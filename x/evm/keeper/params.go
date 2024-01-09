package keeper

import (
	sdk "github.com/cosmos/cosmos-sdk/types"

	"github.com/evmos/ethermint/x/evm/types"
)

// GetParams returns the total set of evm parameters.
func (k Keeper) GetParams(ctx sdk.Context) (params types.Params) {
	// TODO: update once https://github.com/cosmos/cosmos-sdk/pull/12615 is merged
	// and released
	for _, pair := range params.ParamSetPairs() {
		k.paramSpace.GetIfExists(ctx, pair.Key, pair.Value)
	}

	return params
}

// SetParams sets the evm parameters to the param space.
func (k Keeper) SetParamsOld(ctx sdk.Context, params types.Params) {
	k.paramSpace.SetParamSet(ctx, &params)
}

func (k Keeper) SetParams(ctx sdk.Context, params types.Params) error {
	if err := params.Validate(); err != nil {
		return err
	}

	store := ctx.KVStore(k.storeKey)
	bz, err := k.cdc.Marshal(&params)
	if err != nil {
		return err
	}

	store.Set(types.KeyPrefixParams, bz)
	return nil
}
