import torch

from o3.irrep import Irreps


def dummy_data(l: int, randomize_data: bool) -> torch.Tensor:
    # creates dummy data for a specific l value
    if randomize_data:
        return torch.randn(2 * l + 1)
    arr = torch.zeros(2 * l + 1)
    arr[0] = 1  # so the array is normalized to length 1
    return arr


def create_irreps_with_dummy_data(id: str, randomize_data=False) -> Irreps:
    data_out = []
    for _irreps_def, num_irreps, l, _parity in Irreps.parse_id(id):
        for _ in range(num_irreps):
            data_out.append(dummy_data(l, randomize_data=randomize_data))
    return Irreps.from_id(id, data_out)
