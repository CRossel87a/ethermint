from pathlib import Path

import pytest
from web3 import Web3

from .network import setup_custom_ethermint, setup_ethermint
from .utils import (
    ADDRS,
    CONTRACTS,
    deploy_contract,
    send_successful_transaction,
    send_transaction,
    w3_wait_for_new_blocks,
)


@pytest.fixture(scope="module")
def custom_ethermint(tmp_path_factory):
    path = tmp_path_factory.mktemp("filters")
    yield from setup_ethermint(path, 26200, long_timeout_commit=True)


@pytest.fixture(scope="module")
def ethermint_indexer(tmp_path_factory):
    path = tmp_path_factory.mktemp("indexer")
    yield from setup_custom_ethermint(
        path, 26660, Path(__file__).parent / "configs/enable-indexer.jsonnet"
    )


@pytest.fixture(
    scope="module", params=["ethermint", "geth", "ethermint-ws", "enable-indexer"]
)
def cluster(request, custom_ethermint, ethermint_indexer, geth):
    """
    run on both ethermint and geth
    """
    provider = request.param
    if provider == "ethermint":
        yield custom_ethermint
    elif provider == "geth":
        yield geth
    elif provider == "ethermint-ws":
        ethermint_ws = custom_ethermint.copy()
        ethermint_ws.use_websocket()
        yield ethermint_ws
    elif provider == "enable-indexer":
        yield ethermint_indexer
    else:
        raise NotImplementedError


def test_basic(cluster):
    w3 = cluster.w3
    assert w3.eth.chain_id == 9000


# Smart contract names
GREETER_CONTRACT = "Greeter"
ERC20_CONTRACT = "TestERC20A"

# ChangeGreeting topic from Greeter contract calculated from event signature
CHANGE_GREETING_TOPIC = Web3.keccak(text="ChangeGreeting(address,string)")
# ERC-20 Transfer event topic
TRANSFER_TOPIC = Web3.keccak(text="Transfer(address,address,uint256)")


def test_get_logs_by_topic(cluster):
    w3: Web3 = cluster.w3

    contract = deploy_contract(w3, CONTRACTS["Greeter"])

    topic = Web3.keccak(text="ChangeGreeting(address,string)")

    # with tx
    tx = contract.functions.setGreeting("world").build_transaction()
    receipt = send_transaction(w3, tx)
    assert receipt.status == 1

    # The getLogs method under the hood works as a filter
    # with the specified topics and a block range.
    # If the block range is not specified, it defaults
    # to fromBlock: "latest", toBlock: "latest".
    # Then, if we make a getLogs call within the same block that the tx
    # happened, we will get a log in the result. However, if we make the call
    # one or more blocks later, the result will be an empty array.
    logs = w3.eth.get_logs({"topics": [topic.hex()]})

    assert len(logs) == 1
    assert logs[0]["address"] == contract.address

    w3_wait_for_new_blocks(w3, 2)
    logs = w3.eth.get_logs({"topics": [topic.hex()]})
    assert len(logs) == 0


def test_pending_transaction_filter(cluster):
    w3: Web3 = cluster.w3
    flt = w3.eth.filter("pending")

    # without tx
    assert flt.get_new_entries() == []  # GetFilterChanges

    w3_wait_for_new_blocks(w3, 1, sleep=0.1)
    # with tx
    txhash = send_successful_transaction(w3)
    assert txhash in flt.get_new_entries()

    # check if tx_hash is valid
    tx = w3.eth.get_transaction(txhash)
    assert tx.hash == txhash

    # without new txs since last call
    assert flt.get_new_entries() == []


def test_block_filter(cluster):
    w3: Web3 = cluster.w3
    flt = w3.eth.filter("latest")

    # without tx
    assert flt.get_new_entries() == []

    # with tx
    send_successful_transaction(w3)
    block_hashes = flt.get_new_entries()
    assert len(block_hashes) >= 1

    # check if the returned block hash is correct
    # getBlockByHash
    block = w3.eth.get_block(block_hashes[0])
    # block should exist
    assert block.hash == block_hashes[0]

    # without new txs since last call
    assert flt.get_new_entries() == []


def test_event_log_filter_by_contract(cluster):
    w3: Web3 = cluster.w3
    contract = deploy_contract(w3, CONTRACTS["Greeter"])
    assert contract.caller.greet() == "Hello"

    # Create new filter from contract
    current_height = hex(w3.eth.get_block_number())
    flt = contract.events.ChangeGreeting.createFilter(fromBlock=current_height)

    # without tx
    assert flt.get_new_entries() == []  # GetFilterChanges
    assert flt.get_all_entries() == []  # GetFilterLogs

    # with tx
    tx = contract.functions.setGreeting("world").build_transaction()
    tx_receipt = send_transaction(w3, tx)
    assert tx_receipt.status == 1

    log = contract.events.ChangeGreeting().processReceipt(tx_receipt)[0]
    assert log["event"] == "ChangeGreeting"

    new_entries = flt.get_new_entries()
    assert len(new_entries) == 1
    assert new_entries[0] == log
    assert contract.caller.greet() == "world"

    # without new txs since last call
    assert flt.get_new_entries() == []
    assert flt.get_all_entries() == new_entries

    # Uninstall
    assert w3.eth.uninstall_filter(flt.filter_id)
    assert not w3.eth.uninstall_filter(flt.filter_id)
    with pytest.raises(Exception):
        flt.get_all_entries()


def test_event_log_filter_by_address(cluster):
    w3: Web3 = cluster.w3

    contract = deploy_contract(w3, CONTRACTS["Greeter"])
    assert contract.caller.greet() == "Hello"

    flt = w3.eth.filter({"address": contract.address})
    flt2 = w3.eth.filter({"address": ADDRS["validator"]})

    # without tx
    assert flt.get_new_entries() == []  # GetFilterChanges
    assert flt.get_all_entries() == []  # GetFilterLogs

    # with tx
    tx = contract.functions.setGreeting("world").build_transaction()
    receipt = send_transaction(w3, tx)
    assert receipt.status == 1

    assert len(flt.get_new_entries()) == 1
    assert len(flt2.get_new_entries()) == 0


def test_get_logs(cluster):
    w3: Web3 = cluster.w3

    contract = deploy_contract(w3, CONTRACTS["Greeter"])

    # without tx
    assert w3.eth.get_logs({"address": contract.address}) == []
    assert w3.eth.get_logs({"address": ADDRS["validator"]}) == []

    # with tx
    tx = contract.functions.setGreeting("world").build_transaction()
    receipt = send_transaction(w3, tx)
    assert receipt.status == 1

    assert len(w3.eth.get_logs({"address": contract.address})) == 1
    assert len(w3.eth.get_logs({"address": ADDRS["validator"]})) == 0
