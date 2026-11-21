"""LightGBM -> ONNX made only of standard tensor ops (Hummingbird GEMM trees), so Edge Impulse
can import it like a neural network. Output: [P(healthy), P(sepsis)]."""
import numpy as np, lightgbm as lgb, onnx, onnxruntime as ort, torch
from hummingbird.ml import convert

X = np.load("out/val_features.npy")
booster = lgb.Booster(model_file="out/model.txt")
trees = convert(booster, "torch", extra_config={"tree_implementation": "gemm"}).model.eval()


class Probs(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, x):
        p = torch.sigmoid(self.m(x))          # [N, 1] = P(sepsis)
        return torch.cat([1 - p, p], dim=1)   # [N, 2] = healthy, sepsis


torch.onnx.export(Probs(trees).eval(), (torch.from_numpy(X[:1]),), "out/model_gemm.onnx",
                  input_names=["features"], output_names=["probs"], opset_version=13, dynamo=False)
m = onnx.load("out/model_gemm.onnx")
print("ops:", sorted({n.op_type for n in m.graph.node}))
s = ort.InferenceSession("out/model_gemm.onnx")
d = max(abs(s.run(None, {"features": X[i:i + 1]})[0][0, 1] - booster.predict(X[i:i + 1])[0]) for i in range(1000))
print("max abs diff vs LightGBM over 1000 rows:", float(d))
