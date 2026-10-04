"""JEV noul 决策层 — 轻量 TypeSafe System One 客户端（std-lib only，fail-open）。

给 graphify 的确定性启发式决策点（惊喜连接保留判定、建议问题价值过滤、
边合并冲突消解等）叠加 JEV 结构化判断。JEV 不生成文本：输入 state + 类型化
问题 → 返回概率/打分 + 校准置信度，代码可直接分支。

纪律（与 metadata-router / jev-decision skill 一致）：
- 出站仅元数据：label / 关系 / 社区成员摘要，绝不送源码片段（>50 行）或 PII。
- 执行阈值：p>0.75 AND conf>0.85（choice/score 带置信度）；noul 返回校准概率
  本身（0.5 为中立），用 ``keep_prob >= 0.75`` 作行动线。
- Fail-open：无 key / 超时 / 限流 / 网络故障一律返回 ``None``，调用方回退
  确定性逻辑，绝不阻塞主流程。

实现说明：本模块刻意不依赖 graphify.llm 与任何第三方库（urllib + json 即可），
与 ``../scripts/jev-decide.py``（CLI 版）共享相同 API 契约。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

API_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"
_TIMEOUT_SECONDS = 4.0
# 决策阈值（metadata-router 红线：p>0.75 AND conf>0.85）
NOUL_ACCEPT = 0.75
CONF_ACCEPT = 0.85

_WEIGHTED_SCORE_THRESHOLD = 1.6


def _api_key() -> str:
    return os.environ.get("TYPESAFE_API_KEY", "").strip()


def _post_json(payload: dict[str, Any], timeout: float | None = None) -> dict[str, Any] | None:
    """POST 到 System One；任何失败返回 None（fail-open）。"""
    key = _api_key()
    if not key:
        return None
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or _TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError,
            TimeoutError, json.JSONDecodeError):
        return None


def _answer(result: dict[str, Any] | None, qid: str) -> dict[str, Any] | None:
    if not result:
        return None
    answers = result.get("answers") or {}
    ans = answers.get(qid)
    if not isinstance(ans, dict):
        return None
    return ans


def jev_noul(state: str, question: str, *, model: str = DEFAULT_MODEL,
              timeout: float | None = None,
              criteria: dict[str, Any] | None = None) -> float | None:
    """JEV 是非判断：返回『是』的校准概率 0~1；不可用返回 None。"""
    q: dict[str, Any] = {"type": "noul", "instructions": question}
    if criteria:
        q["criteria"] = criteria
    payload: dict[str, Any] = {"state": state, "model": model, "questions": {"noul": q}}
    ans = _answer(_post_json(payload, timeout), "noul")
    if not ans:
        return None
    p = ans.get("noul")
    return float(p) if isinstance(p, (int, float)) else None


def jev_choice(state: str, instructions: str, options: dict[str, Any], *,
               model: str = DEFAULT_MODEL, timeout: float | None = None,
               qid: str = "choice") -> dict[str, Any] | None:
    """JEV 选项选择：返回 {choice, probabilities, confidence}；不可用返回 None。"""
    payload: dict[str, Any] = {
        "state": state,
        "model": model,
        "questions": {qid: {"type": "choice", "instructions": instructions, "criteria": options}},
    }
    ans = _answer(_post_json(payload, timeout), qid)
    if not ans:
        return None
    if "choice" not in ans:
        return None
    conf = ans.get("confidence")
    return {
        "choice": ans["choice"],
        "probabilities": ans.get("probabilities") or {},
        "confidence": float(conf) if isinstance(conf, (int, float)) else None,
    }


def jev_score(state: str, instructions: str, levels: list[Any], *,
              model: str = DEFAULT_MODEL, timeout: float | None = None,
              qid: str = "score") -> dict[str, Any] | None:
    """JEV 打分：返回 {score, probabilities, confidence, legend}；不可用返回 None。"""
    payload: dict[str, Any] = {
        "state": state,
        "model": model,
        "questions": {qid: {"type": "score", "instructions": instructions, "criteria": levels}},
    }
    ans = _answer(_post_json(payload, timeout), qid)
    if not ans:
        return None
    if "score" not in ans:
        return None
    conf = ans.get("confidence")
    return {
        "score": float(ans["score"]) if isinstance(ans["score"], (int, float)) else None,
        "probabilities": ans.get("probabilities") or {},
        "confidence": float(conf) if isinstance(conf, (int, float)) else None,
        "legend": ans.get("legend") or {},
    }


def _conf_ok(conf: float | None) -> bool:
    return conf is not None and conf >= CONF_ACCEPT


def decide_keep(p: float | None, conf: float | None = None) -> bool | None:
    """通用行动线：p>0.75 且（有置信度时）conf>0.85。低置信度/不可用返回 None（回退）。"""
    if p is None:
        return None
    if conf is not None and conf < CONF_ACCEPT:
        return None
    return p >= NOUL_ACCEPT


def score_positive(value: float | None, conf: float | None = None,
                   threshold: float = _WEIGHTED_SCORE_THRESHOLD) -> bool | None:
    """score 行动线：加权分高于阈值且置信度达标 → True；否则 False / None（回退）。"""
    if value is None:
        return None
    if conf is not None and conf < CONF_ACCEPT:
        return None
    return value >= threshold


def score_positive_from(
    result: dict[str, Any] | None,
    threshold: float = _WEIGHTED_SCORE_THRESHOLD,
) -> bool | None:
    """score 行动线（字典入参）：从 JEV score 结果里取加权分与置信度。"""
    if not result:
        return None
    return score_positive(result.get("score"), result.get("confidence"), threshold)


# ---------------------------------------------------------------------------
# 决策点专用判定（薄封装，出站仅元数据）
# ---------------------------------------------------------------------------

def judge_surprise_keep(label_a: str, label_b: str, relation: str, why: str,
                        source_files: list[str] | None = None, *,
                        timeout: float | None = None) -> bool | None:
    """D3 惊喜连接保留判定：'这条跨仓库/跨社区连接是否属于真正意外且有价值的架构发现'。

    返回 True=保留、False=丢弃、None=JEV 不可用（回退原逻辑）。
    """
    state = (
        f"knowledge-graph edge: `{label_a}` --[{relation}]--> `{label_b}`"
        + (f" (files: {', '.join(source_files)})" if source_files else "")
        + f"; heuristic why: {why}"
    )
    return decide_keep(
        jev_noul(state, "这条连接是否属于真正意外且有价值的架构发现（而非结构性噪音/常规依赖）？",
                 timeout=timeout,
                 criteria={
                     "true": "非显然的跨模块/跨社区耦合，揭示真实架构含义",
                     "false": "常规调用、文件结构必然性连接或提取噪音",
                 }),
    )


def judge_question_value(question_type: str, question: str, why: str, *,
                         timeout: float | None = None) -> bool | None:
    """D6 建议问题价值过滤：'这个问题对理解代码库是否值得回答'。"""
    state = f"proposed question [{question_type}]: {question}; signal: {why}"
    return score_positive_from(
        jev_score(state, "这个问题对理解代码库是否有价值？",
                  ["低价值/模板化问题", "有些价值", "高价值洞察问题"],
                  timeout=timeout),
    )


def judge_dedup_same(label_a: str, label_b: str,
                     source_a: str, source_b: str, *,
                     timeout: float | None = None) -> bool | None:
    """D10 边/实体合并冲突消解：'这两个 label 是否描述同一真实世界概念'。

    仅出站 label + source_file（元数据）。
    """
    state = (
        f"entity A: {label_a!r} (from {source_a!r}); entity B: {label_b!r} (from {source_b!r})"
    )
    return decide_keep(
        jev_noul(state, "这两个 label 是否描述同一真实世界概念（应合并为一个实体）？",
                 timeout=timeout,
                 criteria={
                     "true": "同一实体：命名变体/缩写/翻译/明显笔误",
                     "false": "不同实体：同名字段、同名前缀的不同事物、不同模块的平行实现",
                 }),
    )


def judge_label_quality(community_members: list[str], label: str, *,
                        timeout: float | None = None) -> bool | None:
    """D8 社区标签质量校验：LLM 给出的名字是否准确概括社区。"""
    state = (
        f"community members (labels only): {', '.join(community_members[:40])}"
        f"; proposed name: {label!r}"
    )
    return score_positive_from(
        jev_score(state, "这个名字是否准确概括了社区成员？",
                  ["不准确/无关", "部分准确", "准确概括社区"],
                  timeout=timeout),
    )


def judge_god_noise(label: str, source_file: str = "", *,
                    timeout: float | None = None) -> bool | None:
    """D1 god 噪音判断：'这个高连通节点是否属于内置/框架噪音符号（应从 god nodes 排除）'。"""
    state = f"high-degree node label: {label!r}" + (f" (file: {source_file!r})" if source_file else "")
    return decide_keep(
        jev_noul(state, "该符号是否属于编程语言内置类型/框架噪音/样板符号（应从核心抽象排名中排除）？",
                 timeout=timeout,
                 criteria={
                     "true": "内置类型、stdlib、框架符号、Mock 工具、样板关键字",
                     "false": "项目自身的真实抽象",
                 }),
    )


def available() -> bool:
    """JEV 是否可用（仅探测 key，不发起网络调用）。"""
    return bool(_api_key())


__all__ = [
    "API_URL", "DEFAULT_MODEL", "NOUL_ACCEPT", "CONF_ACCEPT",
    "jev_noul", "jev_choice", "jev_score",
    "decide_keep", "score_positive",
    "judge_surprise_keep", "judge_question_value", "judge_dedup_same",
    "judge_label_quality", "judge_god_noise",
    "available",
]
