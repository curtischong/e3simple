from constants import EVEN_PARITY, ODD_PARITY
from irrep import Irrep, Irreps
from spherical_harmonics import map_3d_feats_to_spherical_harmonics_repr
# from tensor_product import tensor_product_v1, tensor_product_v2
import jax.numpy as jnp
import e3nn_jax
import torch

def test_matches_e3nn():
    feat1 = jnp.array([1,1,1])
    feat2 = jnp.array([1,1,2])

    # irrep1 = map_3d_feats_to_spherical_harmonics_repr(jnp.expand_dims(feat1, axis=0))
    # irrep2 = map_3d_feats_to_spherical_harmonics_repr(jnp.expand_dims(feat2, axis=0))

    # print ("e3j irreps:")
    # print(irrep1)
    # print(irrep2)

    # print(tensor_product_v1(irrep1, irrep2).tolist())


    e3nn_irrep1 = e3nn_jax.spherical_harmonics("1x0e + 1x1o", feat1, normalize=True, normalization="norm")
    e3nn_irrep2 = e3nn_jax.spherical_harmonics("1x0e + 1x1o", feat2, normalize=True, normalization="norm")
    print("e3nn irreps:")
    print(e3nn_irrep1)
    print(e3nn_irrep2)
    print("e3nn tensor product:")
    print(e3nn_jax.tensor_product(e3nn_irrep1, e3nn_irrep2,irrep_normalization="component"))

    irreps1 = Irreps([
        Irrep.from_id("0e", torch.tensor(e3nn_irrep1["0e"].chunks[0].tolist()[0])),
        Irrep.from_id("1o", torch.tensor(e3nn_irrep1["1o"].chunks[0].tolist()[0])),
    ])
    irreps2 = Irreps([
        Irrep.from_id("0e", torch.tensor(e3nn_irrep2["0e"].chunks[0].tolist()[0])),
        Irrep.from_id("1o", torch.tensor(e3nn_irrep2["1o"].chunks[0].tolist()[0])),
    ])

    print("e3simple irreps:")
    print(irreps1)
    print(irreps2)
    print("e3simple tensor product:")

    tp = irreps1.tensor_product(irreps2)
    print(tp)
    assert False


if __name__ == "__main__":
    # test_same_results_across_versions()
    test_matches_e3nn()