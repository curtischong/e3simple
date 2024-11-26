# this is the same as tetris.py, except it doesn't use message passing and only uses basis functions to test equivariance
# the model is smaller and faster to train


from geometric_utils import avg_irreps_with_same_id
from irrep import Irreps
from model import LinearLayer
from spherical_harmonics import (
    map_3d_feats_to_basis_functions,
)
from tetris import tetris
import torch.nn as nn
import torch


class TensorDense(nn.Module):
    # perform a tensor product with two linear projections of itself
    def __init__(self, in_irreps_id: str, linear_out_id: str, out_irreps_id: str):
        super().__init__()
        self.linear1 = LinearLayer(in_irreps_id, linear_out_id)
        self.linear2 = LinearLayer(in_irreps_id, linear_out_id)

        tensor_product_output_irreps_id = Irreps.get_tensor_product_output_irreps_id(
            linear_out_id, linear_out_id
        )

        self.linear3 = LinearLayer(
            tensor_product_output_irreps_id, out_irreps_id
        )  # this last one is to combine the result of the tensor product into the target irreps i

    def forward(self, x: Irreps) -> Irreps:
        x1: Irreps = self.linear1(x)
        x2: Irreps = self.linear2(x)
        tp = x1.tensor_product(x2)
        return self.linear3(tp)


class SimpleModel(nn.Module):
    def __init__(self, num_classes: int):
        super().__init__()
        self.tensor_dense1 = TensorDense("8x0e + 1x1o + 1x2e", "6x0e + 4x1o", "6x0e")
        # self.tensor_dense2 = TensorDense("8x0e + 2x1o", "8x0e + 2x1o", "6x0e")
        self.output_mlp = nn.Linear(6, num_classes)

    def forward(self, positions):
        positions -= torch.mean(positions, keepdim=True, dim=-2)
        x = map_3d_feats_to_basis_functions(positions, num_scalar_feats=8, max_l=2)
        x = avg_irreps_with_same_id(x)
        x: Irreps = self.tensor_dense1(x)
        # x: Irreps = self.tensor_dense2(x)
        scalar_feats = [irrep.data for irrep in x.get_irreps_by_id("0e")]
        return self.output_mlp(torch.cat(scalar_feats))


def train_tetris_simple() -> None:
    x, y = tetris()
    model = SimpleModel(y.shape[-1])
    optim = torch.optim.Adam(model.parameters(), lr=0.05)

    for step in range(300):
        # for i, positions in enumerate(x):
        #     pred = model(positions)
        #     loss = (pred - y[i]).pow(2).sum()

        #     loss.backward()
        #     optim.step()

        #     p.step()

        optim.zero_grad()
        loss = torch.zeros(1)
        for i, positions in enumerate(x):
            pred: torch.Tensor = model(positions)
            loss += (pred - y[i]).pow(2).sum()
        loss.backward()
        print(f"loss {loss.item():<10.20f}")

        # torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optim.step()

        if step % 10 == 0:
            for name, param in model.named_parameters():
                if param.grad is not None:
                    print(f"{name}_______", param.grad.tolist())
                else:
                    print(f"{name}_______")

            current_accuracy = 0
            for i, positions in enumerate(x):
                pred = model(positions)
                print("raw pred", pred.tolist())
                one_hot = torch.zeros_like(pred)
                predicted_class = torch.argmax(pred, dim=0)
                one_hot[predicted_class] = 1
                print("pred", one_hot.tolist())
                print("targ", y[i].tolist())
                accuracy = (
                    model(positions)
                    .argmax(dim=0)
                    .eq(y[i].argmax(dim=0))
                    .double()
                    .item()
                )
                current_accuracy += accuracy
            current_accuracy /= len(x)
            print(f"epoch {step:5d} | {100 * current_accuracy:5.1f}% accuracy")
            if current_accuracy == 1.0:
                break
    model_location = "tetris_simple.mp"
    print("saving model to", model_location)
    torch.save(model.state_dict(), model_location)


if __name__ == "__main__":
    train_tetris_simple()
