from __future__ import annotations
from collections import defaultdict
import math
from typing import Generator
import torch
import dataclasses
import re
import e3x
import numpy as np

from utils.constants import EVEN_PARITY, ODD_PARITY
from o3.clebsch_gordan import get_clebsch_gordan
from utils.rot_utils import D_from_matrix
from utils.spherical_harmonics_utils import parity_to_str, to_cartesian_order_idx


def comparison_key(l: int, parity: int) -> tuple[int, int]:
    # first sort by l. Then sort by the parity that is NOT the pseudotensor parity
    return (
        l,
        -parity * (-1) ** l,
    )


class Irreps:
    # this class contains a list of irreps.
    irreps: list[
        Irrep
    ]  # this is always sorted from smallest l to largest l and odd parity to even parity

    def __init__(self, irreps_list: list[Irrep]):
        assert irreps_list, "irreps_list must not be empty"
        self.irreps = self._sort_irreps(irreps_list)

    def _sort_irreps(self, irreps_list: list[Irrep]):
        return sorted(
            irreps_list, key=lambda irrep: comparison_key(irrep.l, irrep.parity)
        )

    @staticmethod
    def from_id(id: str, data: list[torch.Tensor]) -> Irreps:
        assert type(data) is list, "data must be a list of pytorch tensors"
        data_idx = 0  # advance to the next data when we create the next Irrep object
        irreps = []
        for irrep_def, num_irreps, l, parity in Irreps.parse_id(id):
            for _ in range(int(num_irreps)):
                if data_idx >= len(data):
                    raise ValueError(
                        f"not enough data for the irrep {irrep_def}. you need more than {len(data)} data tensors"
                    )
                irreps.append(Irrep(l, parity, data[data_idx]))
                data_idx += 1

        assert (
            len(irreps) == len(data)
        ), f"the number of irreps ({len(irreps)}) must match the number of data tensors ({len(data)})"
        return Irreps(irreps)

    @staticmethod
    def parse_id(
        id: str,
    ) -> Generator[
        tuple[int, int, int], None, None
    ]:  # yields (irrep_def, num_irreps, l, parity)
        irreps_defs = id.split("+")
        irreps_defs = [irrep_def.strip() for irrep_def in irreps_defs]
        irreps_pattern = r"^(\d+)x+(\d+)([eo])$"

        irrep_parts = []
        for irrep_def in irreps_defs:
            # create irreps from the string
            match = re.match(irreps_pattern, irrep_def)
            if not bool(match):
                raise ValueError(
                    f"irrep_def {irrep_def} is not valid. it need to look something like: 1x1o + 1x2e + 1x3o"
                )
            num_irreps, l_str, parity_str = match.groups()

            l = int(l_str)
            parity = ODD_PARITY if parity_str == "o" else EVEN_PARITY
            irrep_parts.append((irrep_def, int(num_irreps), l, parity))
        for parts in sorted(
            irrep_parts, key=lambda x: comparison_key(x[2], x[3])
        ):  # sort by l and parity
            yield parts

    def __repr__(self) -> str:
        return f"{self.id()}: {str(self.data_flattened())}"

    # tells you how many irreps are in the object
    # e.g. 1x2o+3x4e means there is:
    #   1 irrep with l=2 and parity=odd. We need 1*5=5 coefficients to represent this. This is represented as 1 irrep (in the irreps list)
    #   3 irreps with l=4 and parity=even. We need 3*9=27 coefficients to represent this. This is represented as 3 irreps (in the irreps list)
    # In total, there are: 32 coefficients spanning across 4 irreps
    def id(self):
        irrep_ids_with_cnt = []
        current_id = self.irreps[0].id()
        irrep_of_same_id_cnt = 1

        for irrep in self.irreps[1:]:
            if irrep.id() == current_id:
                irrep_of_same_id_cnt += 1
            else:
                irrep_ids_with_cnt.append(f"{irrep_of_same_id_cnt}x{current_id}")
                current_id = irrep.id()
                irrep_of_same_id_cnt = 1

        # Append the last group
        irrep_ids_with_cnt.append(f"{irrep_of_same_id_cnt}x{current_id}")

        return "+".join(irrep_ids_with_cnt)

    def tensor_product(
        self,
        other: Irreps,
        compute_up_to_l: int = None,
        norm_type: str = "component",
    ) -> Irreps:
        new_irreps = []
        for irrep1 in self.irreps:
            for irrep2 in other.irreps:
                new_irreps.extend(
                    irrep1.tensor_product(irrep2, compute_up_to_l, norm_type)
                )
        return Irreps(new_irreps)

    @staticmethod
    def get_tensor_product_output_irreps_id(
        irreps_id1: str, irreps_id2: str, compute_up_to_l: int = None
    ) -> str:
        id_cnt = defaultdict(int)
        unique_ids = set()
        for _irreps_def, num_irreps1, l1, parity1 in Irreps.parse_id(irreps_id1):
            for _irreps_def, num_irreps2, l2, parity2 in Irreps.parse_id(irreps_id2):
                l_min = abs(l1 - l2)
                l_max = l1 + l2
                if compute_up_to_l is not None:
                    l_max = min(l_max, compute_up_to_l)
                parity_out = parity1 * parity2
                for l_out in range(l_min, l_max + 1):
                    unique_ids.add((l_out, parity_out))
                    id_cnt[(l_out, parity_out)] += num_irreps1 * num_irreps2

        # sort by l and parity
        sorted_ids = sorted(unique_ids, key=lambda x: comparison_key(x[0], x[1]))
        output_ids = []
        for id in sorted_ids:
            output_ids.append(f"{id_cnt[id]}x{id[0]}{parity_to_str(id[1])}")
        return "+".join(output_ids)

    def data(self):
        return [irrep.data for irrep in self.irreps]

    def data_flattened(self) -> list[float]:
        consolidated_data = []
        for irrep in self.irreps:
            consolidated_data.extend(irrep.data.tolist())
        return consolidated_data

    def data_flattened_tensor(self) -> torch.Tensor:
        return torch.cat([irrep.data.flatten() for irrep in self.irreps])

    def get_irreps_by_id(self, id: str) -> list[Irrep]:
        return [irrep for irrep in self.irreps if irrep.id() == id]

    @staticmethod
    def count_num_irreps(
        irreps_id: str,
    ) -> tuple[defaultdict[int, int], list[tuple[str, int, int]]]:
        irrep_id_cnt = defaultdict(int)
        sorted_ids = []

        for _irrep_def, num_irreps, l, parity in Irreps.parse_id(irreps_id):
            irrep_id = Irrep.to_id(l, parity)
            sorted_ids.append((irrep_id, l, parity))
            irrep_id_cnt[irrep_id] += num_irreps
        return (irrep_id_cnt, sorted_ids)

    # after irreps are transformed under a group action, they rotate predictably by the wigner-d matrix
    def rotate_with_wigner_d_rot_matrix(self, r3_rot_mat: torch.Tensor) -> Irreps:
        new_irreps = []
        for irrep in self.irreps:
            D = D_from_matrix(r3_rot_mat, irrep.l, parity=irrep.parity)

            new_irreps.append(Irrep(irrep.l, irrep.parity, data=irrep.data @ D.T))
        return Irreps(new_irreps)

    def rotate_with_wigner_d_rot_matrix2(self, r3_rot_mat: torch.Tensor) -> Irreps:
        new_irreps = []
        max_l = max([irrep.l for irrep in self.irreps])
        D_full = np.asarray(e3x.so3.wigner_d(r3_rot_mat.numpy(), max_degree=max_l))

        for irrep in self.irreps:
            start = irrep.l**2
            stop = (irrep.l + 1) ** 2
            D = torch.from_numpy(D_full[start:stop, start:stop])

            new_irreps.append(Irrep(irrep.l, irrep.parity, data=irrep.data @ D.T))
        return Irreps(new_irreps)

    ###########################################################################
    # GNN Utils
    # These are utils that are used by the neural network framework to actually make predictions from the irreps
    ###########################################################################

    # since tensor products create many irreps, often of the same id,
    # often times, we don't want this much data to be stored in memory.
    # so we average the irreps of the same id together so we only get one irrep per id
    # TODO: write a test for this
    # Note: this isn't used anymore since we are using linear layers to do a weighted sum of irreps
    def avg_irreps_of_same_id(self):
        id_to_representation = defaultdict(list[Irrep])
        for irrep in self.irreps:
            id_to_representation[irrep.id()].append(irrep)

        new_irreps = []
        for representations in id_to_representation.values():
            num_representation = len(representations)

            # we will use representations[0] as the irrep we'll sum all the other irreps onto
            for representation in representations[1:]:
                representations[0].data += representation.data
            representations[0].data /= num_representation
            new_irreps.append(representations[0])
        self.irreps = self._sort_irreps(new_irreps)


@dataclasses.dataclass(init=False)
class Irrep:
    # this class contains the coefficients for 2*l + 1 spherical harmonics of degree l and parity p
    l: int  # determines: "which order of spherical harmonics we are dealing with". if l=3, this irrep carries the data for spherical harmonics of degree 3. there are 2*3+1 = 7 spherical harmonics of degree 3. so we need 7 coefficients to represent this
    parity: int  # Note: the parity doesn't determine the NUMBER of coefficients. It's just used to determine the the parity of irreps resulting from tensor products
    data: torch.Tensor

    def __init__(self, l: int, parity: int, data: torch.Tensor):
        assert l >= 0, "l (the degree of your representation) must be non-negative"
        assert (
            parity in {EVEN_PARITY, ODD_PARITY}
        ), f"p (the parity of your representation) must be 1 (even) or -1 (odd). You passed in {parity}"
        assert (
            data.numel() == 2 * l + 1
        ), f"Expected {2*l + 1} coefficients for l={l}, parity={parity}. Got {data.numel()} coefficients instead"
        assert (
            data.dim() == 1
        ), f"data array passed to irrep is {data.dim}-dimensional. Please make sure it's 1D instead"
        self.l = l
        self.parity = parity
        self.data = data

    @staticmethod
    def from_id(irrep_id: str, data: torch.Tensor):
        irrep_pattern = r"^(\d+)([eo])$"
        match = re.match(irrep_pattern, irrep_id)
        if not bool(match):
            raise ValueError(
                f"irrep_id {irrep_id} is not valid. it need to look something like: 1o or 7e. (this is the order l followed by the parity (e or o)"
            )

        l_str, parity_str = match.groups()
        parity = -1 if parity_str == "o" else 1

        return Irrep(int(l_str), parity, data)

    def get_coefficient(self, m: int) -> float:
        return self.data[to_cartesian_order_idx(self.l, m)]

    def tensor_product(
        self, irrep2: Irrep, compute_up_to_l: int, norm_type: str
    ) -> list[Irrep]:
        irrep1 = self

        l1 = irrep1.l
        l2 = irrep2.l
        l_min = abs(l1 - l2)
        l_max = l1 + l2

        if compute_up_to_l is not None:
            # tensor products create many new irreps (including those with large l).
            # sometimes we don't care about higher orders of l since it doesn't increase accuracy that much (and requires calculating more coefficients)
            l_max = min(l_max, compute_up_to_l)

        parity_out = irrep1.parity * irrep2.parity

        res_irreps = []

        # the tensor product of these two irreps will generate (max_l+1 - min_l) new irreps. where each new irrep has l=l_out and parity=parity_out
        for l_out in range(l_min, l_max + 1):
            # calculate all 2l+1 coefficients for this irrep here
            coefficients = torch.zeros(2 * l_out + 1)
            for m3 in range(-l_out, l_out + 1):
                # here we are doing the summation to get the coefficient for this m3 (see assets/tensor_product.png for the formula)
                m3_idx = to_cartesian_order_idx(l_out, m3)
                for m1 in range(-l1, l1 + 1):
                    for m2 in range(-l2, l2 + 1):
                        cg = get_clebsch_gordan(l1, l2, l_out, m1, m2, m3)
                        v1 = irrep1.get_coefficient(m1)
                        v2 = irrep2.get_coefficient(m2)
                        normalization_const = (
                            self._get_tensor_product_normalization_constant(
                                l1, l2, l_out, norm_type
                            )
                        )
                        coefficients[m3_idx] += cg * v1 * v2 * normalization_const

            res_irreps.append(Irrep(l_out, parity_out, coefficients))
        return res_irreps

    def _get_tensor_product_normalization_constant(
        self,
        l1: int,
        l2: int,
        l_out: int,
        norm_type: str,
    ) -> float:
        if norm_type == "component":
            return math.sqrt(2 * l_out + 1)
        elif norm_type == "norm":
            return math.sqrt((2 * l1 + 1) * (2 * l2 + 1))
        elif norm_type == "none":
            return 1
        else:
            raise ValueError(f"normalization={norm_type} not supported")

    def __repr__(self) -> str:
        id = self.id()
        return f"{id}: {self.data.tolist()}"

    # tells you what type of irrep this is
    # e.g. 2o means it's for spherical harmonics of degree 2 (l=2) and parity=odd
    # since l=2, there are 2*2 + 1 = 5 coefficients that this irrep stores in its data array
    def id(self):
        return Irrep.to_id(self.l, self.parity)

    @staticmethod
    def to_id(l: int, parity: int) -> str:
        if parity == 1:
            parity_str = "e"
        elif parity == -1:
            parity_str = "o"
        return f"{l}{parity_str}"
