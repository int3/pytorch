# Owner(s): ["module: inductor"]
from torch.testing._internal.inductor_utils import HAS_CPU, HAS_CUDA
from torch.testing._internal.common_utils import (
    TEST_WITH_ASAN,
    TestCase as TorchTestCase,
)
import os
import math
import sys
import torch

# Make the helper files in test/ importable
pytorch_test_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(pytorch_test_dir)

from inductor.test_torchinductor import check_model_cuda, check_model, copy_tests
import contextlib
from torch._inductor import config
from torch._inductor.scheduler import Scheduler
import unittest


class TestCase(TorchTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._stack = contextlib.ExitStack()
        cls._stack.enter_context(
            config.patch({
                "benchmark_kernel": True,
                "benchmark_fusion": True,
            })
        )

    @classmethod
    def tearDownClass(cls):
        cls._stack.close()
        super().tearDownClass()

class BenchmarkFusionTestTemplate:
    def test_softmax(self):
        def f(x):
            return torch.nn.functional.softmax(x, dim=-1)

        self.common(f, (torch.rand(2, 8192),))

    def test_resnet18(self):
        import torchvision
        model = torchvision.models.resnet18()
        model.eval()
        batch_size = 16
        inputs = (torch.randn((batch_size, 3, 224, 224)),)
        self.common(model, inputs, atol=1e-2, rtol=1e-2)

    def test_register_spills(self):
        """
        The test can potentially trigger register spills
        """
        old_benchmark_fn = Scheduler.benchmark_fused_nodes
        def new_benchmark_fn(scheduler, nodes):
            """
            We override Scheduler.benchmark_fused_nodes to return latency 1.0
            if there are no register spills. Without this, we may not able to
            test the code path handling register spilling because before register
            start spilling, the related fusion may have already been skipped
            due to longer lantency.
            """
            ms = old_benchmark_fn(scheduler, nodes)
            if not math.isinf(ms):
                ms = 1.0
            return ms

        # Disable dynamic_scale_rblock to make it easier to trigger register
        # spilling.
        with unittest.mock.patch.object(Scheduler, "benchmark_fused_nodes", new_benchmark_fn), config.patch("dynamic_scale_rblock", False):
            S = 512
            def f(*inputs):
                inputs = list(inputs)
                outputs = []
                out = torch.zeros(S).cuda()
                for x in inputs:
                    x = x * 2
                    x = x + 1
                    x = x.sum(dim=-1)
                    outputs.append(x)
                    out = out + x
                return outputs, out
    
            N = int(os.environ.get("NINP", "30"))
            inputs = [torch.randn(S, 2560).cuda() for _ in range(N)]
            opt_f = torch.compile(f)
            opt_f(*inputs)

if HAS_CUDA and not TEST_WITH_ASAN:
    class BenchmarkFusionCudaTest(TestCase):
        common = check_model_cuda
        device = "cuda"

    copy_tests(BenchmarkFusionTestTemplate, BenchmarkFusionCudaTest, "cuda")

if HAS_CPU and not torch.backends.mps.is_available():
    class BenchmarkFusionCpuTest(TestCase):
        common = check_model
        device = "cpu"

    copy_tests(BenchmarkFusionTestTemplate, BenchmarkFusionCpuTest, "cpu")

if __name__ == "__main__":
    from torch._dynamo.test_case import run_tests
    if HAS_CPU or HAS_CUDA:
        run_tests()
