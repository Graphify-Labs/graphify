import os
import unittest
from unittest.mock import patch
import networkx as nx

from graphify.jev_bridge import (
    is_available,
    pick_seeds_with_jev,
    _call_jev_choice,
    _SEED_CACHE
)
from graphify.jev_pruner import prune_bfs_neighbors_with_jev
from graphify.jev_audit import analyze_blast_radius
from graphify.serve import _query_graph_text


class TestJevPRFeatures(unittest.TestCase):
    def setUp(self):
        _SEED_CACHE.clear()
        self.G = nx.DiGraph()
        
        # 社区 1: auth
        self.G.add_node("auth_service", label="auth_service.py", file_type="code", source_file="services/auth.py", source_location="L1")
        self.G.add_node("fn_login", label="login()", source_file="services/auth.py", source_location="L10", docstring="用户登录")
        self.G.add_node("fn_token", label="refresh_token()", source_file="services/auth.py", source_location="L20", docstring="刷新Token")
        self.G.add_edge("auth_service", "fn_login", relation="contains")
        self.G.add_edge("auth_service", "fn_token", relation="contains")

        # 社区 2: payment
        self.G.add_node("payment_service", label="payment.py", file_type="code", source_file="services/payment.py", source_location="L1")
        self.G.add_node("fn_pay", label="pay()", source_file="services/payment.py", source_location="L10", docstring="发起支付")
        self.G.add_edge("payment_service", "fn_pay", relation="contains")

        # 跨模块调用关系：fn_login 依赖 fn_token
        self.G.add_edge("fn_login", "fn_token", relation="calls")

    def test_fail_open_when_no_api_key(self):
        """测试在无 API KEY 时，严格 fail-open 返回 None"""
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "", "OPENCODE_API_KEY": ""}, clear=True):
            self.assertFalse(is_available())
            seeds = pick_seeds_with_jev(self.G, "用户登录")
            self.assertIsNone(seeds)

    def test_fail_open_on_network_error(self):
        """测试网络超时或异常时，静默返回 None"""
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "fake_key"}):
            with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
                res = _call_jev_choice("state", "instr", {"opt1": "desc1"})
                self.assertIsNone(res)
                seeds = pick_seeds_with_jev(self.G, "用户登录")
                self.assertIsNone(seeds)

    @patch("graphify.jev_bridge._call_jev_choice")
    def test_successful_two_stage_picking(self, mock_choice):
        """测试在 JEV 正常响应时，成功完成两阶段语义寻种"""
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "fake_key"}):
            mock_choice.side_effect = [
                ("0", 0.95, {"0": 0.95, "1": 0.05}),
                ("fn_token", 0.99, {"fn_token": 0.99, "fn_login": 0.01})
            ]
            seeds = pick_seeds_with_jev(self.G, "刷新Token凭证")
            self.assertEqual(seeds, ["fn_token"])

    @patch("graphify.jev_bridge._call_jev_choice")
    def test_multi_candidate_cross_community_support(self, mock_choice):
        """测试多候选概率取种（跨社区）"""
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "fake_key"}):
            mock_choice.side_effect = [
                ("0", 0.52, {"0": 0.52, "1": 0.48}),
                ("fn_token", 0.95, {"fn_token": 0.95}),
                ("fn_pay", 0.96, {"fn_pay": 0.96})
            ]
            seeds = pick_seeds_with_jev(self.G, "支付后刷新Token", max_seeds=2)
            self.assertIn("fn_token", seeds)
            self.assertIn("fn_pay", seeds)
            self.assertEqual(len(seeds), 2)

    @patch("graphify.jev_bridge._call_jev_choice")
    def test_lru_caching_performance(self, mock_choice):
        """测试基于图谱状态与查询指纹的 0ms 内存缓存"""
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "fake_key"}):
            mock_choice.side_effect = [
                ("0", 0.95, {"0": 0.95}),
                ("fn_login", 0.99, {"fn_login": 0.99})
            ]
            seeds1 = pick_seeds_with_jev(self.G, "用户如何登录")
            self.assertEqual(seeds1, ["fn_login"])
            self.assertEqual(mock_choice.call_count, 2)

            seeds2 = pick_seeds_with_jev(self.G, "用户如何登录")
            self.assertEqual(seeds2, ["fn_login"])
            self.assertEqual(mock_choice.call_count, 2)

    def test_evolution_2_blast_radius(self):
        """测试进化 2：逆向变更影响面分析（改动 fn_token 会波及上游 fn_login）"""
        report = analyze_blast_radius(self.G, "refresh_token", max_depth=1)
        self.assertEqual(report["target_symbol"], "refresh_token()")
        self.assertGreaterEqual(report["blast_radius_score"], 1)

    @patch("graphify.jev_pruner._call_jev_choice")
    def test_evolution_1_bfs_smart_pruning(self, mock_choice):
        """测试进化 1：BFS 扩散时智能修枝剪断杂草"""
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "fake_key"}):
            mock_choice.return_value = ("fn_login", 0.99, {"fn_login": 0.99})
            raw_neighbors = ["fn_login", "util_logger", "n3", "n4", "n5", "n6"]
            for n in ["util_logger", "n3", "n4", "n5", "n6"]:
                self.G.add_node(n, label=n, source_file="util.py", docstring="工具")
                self.G.add_edge("auth_service", n, relation="calls")
                
            kept = prune_bfs_neighbors_with_jev(self.G, "auth_service", raw_neighbors, "用户登录逻辑", max_keep=3)
            self.assertIn("fn_login", kept)
            self.assertLessEqual(len(kept), 3)


if __name__ == "__main__":
    unittest.main()
