"""④ 改写 rewrite：清洗稿 -> 单个轻度改写稿 -> 人工确认 final_text。"""
from __future__ import annotations

import json
import hashlib
import math
import os
import re
import time
import uuid
from difflib import SequenceMatcher

import config
import compliance
import db
import storage
from rewrite_review import MAX_REVISIONS, PLANNED_MIN_LENGTH_RATIO, PLANNED_TARGET_LENGTH_RATIO, evaluate as review_rewrite, opening_hook, remainder, format_for_reading, effective_length, attempt_rank, length_bounds
from rewrite_skill import resolve_domain, prompt_extension, audit_output, DomainConflict
from prompt_profiles import (
    author_name,
    derive_keyword,
    load_prompt,
    normalize_category,
    protected_terms,
    rewrite_prompt_kind,
)

_CAND_RE = re.compile(r"【候选[ABC]】\s*(.*?)(?=【候选[ABC]】|$)", re.DOTALL)
_client = None
_MAX_COSYVOICE_INSTRUCTION_UNITS = 100


def _request_rewrite(**kwargs):
    """Retry proxy timeout responses without regenerating a different stage."""
    for attempt in range(config.REWRITE_RETRIES + 1):
        try:
            return _llm().chat.completions.create(**kwargs)
        except Exception as exc:
            if 'model_not_found' in str(exc).lower():
                raise
            if not any(code in str(exc) for code in ("502", "503", "504", "524")) or attempt >= config.REWRITE_RETRIES:
                raise
            time.sleep(min(60, 2 ** (attempt + 1)))


def _llm():
    global _client
    if not _client:
        _client = config.rewrite_client()
    return _client


def _text_len(text: str) -> int:
    return effective_length(text)


def _normalized(text: str) -> str:
    return re.sub(r"[\s，。！？；：、,.!?;:'\"“”‘’（）()《》]+", "", text or "")


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalized(left), _normalized(right)).ratio()


def _dialogue_body(text: str) -> str:
    """Remove speaker labels before comparing a dialogue rewrite with its source script."""
    return re.sub(r"(?m)^\s*(?:主持人|嘉宾)\s*[：:]\s*", "", text or "").strip()


def _longest_common_run(left: str, right: str) -> int:
    """Return the longest verbatim normalized span shared by two scripts."""
    source = _normalized(left)
    rewritten = _normalized(right)
    if not source or not rewritten:
        return 0
    return SequenceMatcher(None, source, rewritten, autojunk=False).find_longest_match(
        0, len(source), 0, len(rewritten)
    ).size


def _parse_candidates(raw: str) -> list[str]:
    """Parse a new single draft while retaining legacy artifact compatibility."""
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict) and str(payload.get("text", "")).strip():
            return [str(payload["text"]).strip()]
        items = payload.get("candidates", []) if isinstance(payload, dict) else []
        parsed = [
            str(item.get("text", "")).strip() if isinstance(item, dict) else str(item).strip()
            for item in items
        ]
        if parsed and all(parsed):
            return parsed
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    matches = [m.strip() for m in _CAND_RE.findall(raw)]
    return matches if matches else []


def _instruction_units(value: str) -> int:
    """DashScope counts CJK characters as two instruction characters."""
    return sum(2 if "\u4e00" <= char <= "\u9fff" else 1 for char in value)


def _dialogue_delivery_plan(raw: str, text: str) -> list[dict] | None:
    """Validate editable text and machine-readable podcast direction stay aligned."""
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    plan = payload.get("delivery_plan") if isinstance(payload, dict) else None
    if not isinstance(plan, list) or not plan:
        return None
    normalized: list[dict] = []
    lines: list[str] = []
    for item in plan:
        if not isinstance(item, dict):
            return None
        speaker = str(item.get("speaker") or "").strip()
        turn_text = str(item.get("text") or "").strip()
        instruction = str(item.get("instruction") or "").strip()
        if speaker not in {"主持人", "嘉宾"} or not turn_text or not instruction:
            return None
        if _instruction_units(instruction) > _MAX_COSYVOICE_INSTRUCTION_UNITS:
            return None
        normalized.append({"speaker": speaker, "text": turn_text, "instruction": instruction})
        lines.append(f"{speaker}：{turn_text}")
    expected = "\n".join(lines)
    if re.sub(r"\s+", "", expected) != re.sub(r"\s+", "", text or ""):
        return None
    return normalized


def _rewrite_structure(raw: str, text: str) -> dict:
    """Optional presentation metadata; the plain text contract stays canonical."""
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        payload = {}
    hook = str(payload.get("hook") or "").strip() if isinstance(payload, dict) else ""
    strategy = str(payload.get("hook_strategy") or "").strip() if isinstance(payload, dict) else ""
    paragraphs = payload.get("paragraphs") if isinstance(payload, dict) else None
    if not isinstance(paragraphs, list) or not all(isinstance(item, str) and item.strip() for item in paragraphs):
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n|\n", text) if item.strip()]
    if not hook:
        hook = paragraphs[0] if paragraphs else text[:120]
    cta_original = str(payload.get("cta_original") or "").strip() if isinstance(payload, dict) else ""
    cta_revised = str(payload.get("cta_revised") or "").strip() if isinstance(payload, dict) else ""
    cta_range = payload.get("cta_range") if isinstance(payload, dict) else None
    if not isinstance(cta_range, dict):
        cta_range = {}
    book_title = str(payload.get("book_title") or "").strip() if isinstance(payload, dict) else ""
    book_title_source = str(payload.get("book_title_source") or ("reference_copy" if book_title else "absent")).strip()
    hook_text = str(payload.get("hook_text") or hook).strip() if isinstance(payload, dict) else hook
    body_text = str(payload.get("body_text") or "").strip() if isinstance(payload, dict) else ""
    tail_text = str(payload.get("tail_text") or "").strip() if isinstance(payload, dict) else ""
    return {
        "hook": hook,
        "cover_options": [item for item in (payload.get('cover_options',[]) if isinstance(payload,dict) else [])
                          if isinstance(item,dict) and 0 < len(str(item.get('title') or '')) <= 24
                          and 0 < len(str(item.get('subtitle') or '')) <= 36][:3],
        "hook_strategy": strategy or "counter_intuitive",
        "hook_text": hook_text,
        "body_text": body_text,
        "tail_text": tail_text,
        "paragraphs": paragraphs,
        "delivery_plan": _dialogue_delivery_plan(raw, text),
        "cta_original": cta_original,
        "cta_revised": cta_revised,
        "cta_range": {
            "start": max(0, int(cta_range.get("start") or 0)),
            "end": max(0, int(cta_range.get("end") or 0)),
        },
        "book_title": book_title,
        "book_title_source": book_title_source if book_title else "absent",
    }


def _dialogue_structure_issues(text: str) -> list[str]:
    """Keep podcast scripts conversational while leaving domain compliance unchanged."""
    turns: list[tuple[str, str]] = []
    for line in re.split(r"\n+", text or ""):
        match = re.match(r"^(主持人|嘉宾)\s*[：:]\s*(.+)$", line.strip())
        if not match:
            return ["双人播客每段必须以“主持人：”或“嘉宾：”开头"]
        content = match.group(2).strip()
        if len(re.sub(r"\s+", "", content)) < 6:
            return ["双人播客单轮发言过短，无法形成自然问答"]
        if len(re.sub(r"\s+", "", content)) > 90:
            return ["双人播客单轮发言过长，应控制在 90 字以内"]
        turns.append((match.group(1), content))
    if len(turns) < 4:
        return ["双人播客至少需要 4 个交替轮次"]
    if {speaker for speaker, _ in turns} != {"主持人", "嘉宾"}:
        return ["双人播客必须同时包含主持人和嘉宾"]
    if turns[0][0] != "主持人" or "?" not in turns[0][1] and "？" not in turns[0][1]:
        return ["双人播客首轮必须由主持人以问题或反差钩子开启"]
    if not any(speaker == "主持人" and ("?" in content or "？" in content) for speaker, content in turns):
        return ["主持人至少需要提出一个明确问题"]
    same_speaker_turns = 1
    for previous, current in zip(turns, turns[1:]):
        same_speaker_turns = same_speaker_turns + 1 if previous[0] == current[0] else 1
        if same_speaker_turns > 2:
            return ["双人播客同一角色不能连续超过 2 轮，应增加自然承接"]
    return []


def _candidate_issues(
    candidates: list[str],
    source: str,
    finish_reason: str | None,
    mode: str = "initial_dedup",
    category: str = "health",
    narration_mode: str = "single",
) -> list[str]:
    issues: list[str] = []
    if finish_reason == "length":
        issues.append("模型输出达到长度上限")
    if len(candidates) != 1:
        issues.append("未生成一个完整改写稿")
        return issues

    source_len = _text_len(source)
    min_len, max_len = length_bounds(source)
    for i, text in enumerate(candidates):
        if narration_mode == "dual_dialogue":
            issues.extend(_dialogue_structure_issues(text))
        comparison_text = _dialogue_body(text) if narration_mode == "dual_dialogue" else text
        length = _text_len(comparison_text)
        if narration_mode != "dual_dialogue":
            if length < min_len:
                issues.append(f"改写稿过短（{length}/{source_len} 字）")
            if length > max_len:
                issues.append(f"改写稿明显超出原文长度（{length}/{source_len} 字）")
            if not text.lstrip().startswith(opening_hook(source)):
                issues.append("开头黄金钩子未按原文保留")
        if re.search(r"(?:未完待续|请继续|继续输出|\.\.\.|……)\s*$", text):
            issues.append("改写稿疑似被截断")
        if text.rstrip().endswith(("，", ",", "：", ":", "；", ";", "、")):
            issues.append("改写稿结尾不完整")
        for title in re.findall(r"《([^》]+)》", source):
            if f"《{title}》" not in text:
                issues.append(f"未完整保留书名《{title}》")
    return issues


def _candidate_warnings(
    text: str,
    source: str,
    mode: str = "initial_dedup",
    category: str = "health",
    narration_mode: str = "single",
) -> list[str]:
    """Expose style drift for review without blocking an otherwise complete draft."""
    if narration_mode == "dual_dialogue":
        return []
    warnings: list[str] = []
    if category == "health" and mode == "initial_dedup":
        similarity = _similarity(source, text)
        if similarity > 0.72:
            warnings.append(f"健康首发改写与原稿较近（相似度 {similarity:.2f}，建议不高于 0.72）")
        common_run = _longest_common_run(source, text)
        if common_run > 16:
            warnings.append(f"健康首发改写存在较长原句复用（连续 {common_run} 个有效字符）")
    if _similarity(source[:50], text[:50]) < 0.35:
        warnings.append("开头钩子改动较大")
    return warnings


def _rewrite_prompt_kind(category: str, mode: str, narration_mode: str) -> str:
    prompt_kind = rewrite_prompt_kind(mode)
    if narration_mode == "dual_dialogue" and category == "health":
        return f"dual_dialogue_{prompt_kind}"
    return prompt_kind


def _length_budget(source: str, hook: str) -> str:
    """Give the model a concrete coverage budget before it starts drafting."""
    minimum, maximum = length_bounds(source)
    target = math.ceil(effective_length(source) * PLANNED_TARGET_LENGTH_RATIO)
    planned_minimum = math.ceil(effective_length(source) * PLANNED_MIN_LENGTH_RATIO)
    hook_chars = effective_length(hook)
    body = remainder(source, hook)
    paragraphs = [part.strip() for part in format_for_reading(body).split('\n\n') if part.strip()]
    if not paragraphs:
        return f'正文目标约{max(0, target - hook_chars)}字；全文硬性范围{minimum}-{maximum}字。'
    groups: list[list[str]] = []
    ideal = max(180, math.ceil(effective_length(body) / 10))
    for paragraph in paragraphs:
        if not groups or effective_length(''.join(groups[-1])) >= ideal:
            groups.append([])
        groups[-1].append(paragraph)
    sizes = [effective_length(''.join(group)) for group in groups]
    body_target = max(0, target - hook_chars)
    total = max(1, sum(sizes))
    allocations = [body_target * size // total for size in sizes]
    for index in range(body_target - sum(allocations)):
        allocations[index % len(allocations)] += 1
    lines = [
        f'全文写作目标约{target}字（含已锁定钩子{hook_chars}字），'
        f'正文目标约{body_target}字；自动改写的目标下限{planned_minimum}字，'
        f'仅在返工次数用尽时可按执行下限{minimum}字交付，上限{maximum}字。',
        '以下按原稿信息块预留篇幅，顺序可以重组；每块的事实与限定必须有去处，不能用空话凑字：',
    ]
    for index, (group, size, allocation) in enumerate(zip(groups, sizes, allocations), 1):
        anchor = group[0].replace('\n', ' ')[:24]
        lines.append(f'{index}. 原稿约{size}字，改写预留约{allocation}字；识别线索：{anchor}…')
    lines.append('先在 information_card 和 rewrite_outline 中分配所有信息块，再写 rewritten_remainder。提交前自行按有效字口径核算；若不足，补足遗漏的事实、场景或论证，不重复钩子和套话。')
    return '\n'.join(lines)


def _generate_single_candidates(source: str, context: dict, notes: str, mode: str) -> tuple[list[str], list[int], dict]:
    """Initial generation plus at most three content revisions, then human review."""
    hook = opening_hook(source)
    prompt = load_prompt(context['category'], 'initial_dedup')
    skill_profile = context.get('rewrite_skill')
    if skill_profile:
        extension, skill_profile = prompt_extension(skill_profile)
        prompt += '\n\n' + extension
    source_body = remainder(source, hook)
    minimum, maximum = length_bounds(source)
    planned_minimum = math.ceil(effective_length(source) * PLANNED_MIN_LENGTH_RATIO)
    hook_chars = effective_length(hook)
    budget = _length_budget(source, hook)
    history: list[dict] = list(context.get('rewrite_resume') or [])
    checkpoint = context.get('rewrite_checkpoint')
    last: tuple[list[str], list[int], dict] | None = None
    best_rank: tuple | None = None
    stop_reason = 'limit_reached'
    last_issues: list[str] = []
    for saved in history:
        if saved.get('text') and saved.get('structure') and saved.get('similarity'):
            rank = attempt_rank(saved)
            if best_rank is None or rank < best_rank:
                last = ([saved['text']], [_text_len(saved['text'])], json.loads(json.dumps(saved['structure'])))
                selected_attempt = saved['attempt']; best_rank = rank
        last_issues = saved.get('issues', [])
    already_passed = bool(last and not next(item for item in history if item['attempt']==selected_attempt).get('issues'))
    if already_passed:
        stop_reason = 'passed' if next(item for item in history if item['attempt']==selected_attempt)['similarity']['status']=='passed' else 'locked_hook_floor'
    for attempt in range(MAX_REVISIONS + 1 if already_passed else len(history), MAX_REVISIONS + 1):
        feedback = ''
        if history:
            previous = next((item for item in reversed(history) if item.get('text')), history[-1])
            feedback = '\n\n【上一轮稿件】\n' + previous.get('text', '')
            feedback += '\n【必须处理的问题】\n' + '\n'.join(previous.get('issues', last_issues))
            if previous.get('text'):
                previous_chars = effective_length(previous['text'])
                if previous_chars < planned_minimum:
                    feedback += (f'\n上稿有效字数{previous_chars}，距95%写作目标下限还差{planned_minimum - previous_chars}字；'
                                 f'本轮请按上方信息块预算补全，全文目标约{math.ceil(effective_length(source) * PLANNED_TARGET_LENGTH_RATIO)}字。')
            feedback += '\n【可改写区重复片段】\n' + '\n'.join(
                previous.get('similarity', {}).get('unlocked', {}).get('repeated_fragments', []))
        history.append({'attempt':attempt+1,'revision':attempt,'text':'','issues':['请求已预留，未收到完整结果'],'complete':False,'state':'reserved'})
        if checkpoint:
            checkpoint(history)
        request_started = time.monotonic()
        try:
            response = _request_rewrite(
                model=config.REWRITE_MODEL,
                messages=[{'role': 'system', 'content': prompt}, {'role': 'user', 'content': (
                    f"内容分类：{context['category']}；模式：{mode}\n主题：{context.get('keyword', '')}\n"
                    f"原视频标题：{context.get('title', '')}\n补充要求：{notes or '无'}\n"
                    f"必须保留的书名与数字：{'、'.join(protected_terms(source)) or '无'}\n"
                    f"原稿有效字数{effective_length(source)}字；本轮写作须达到{planned_minimum}-{maximum}字，"
                    f"仅在自动返工次数用尽后可按{minimum}字执行下限交付。"
                    f"程序拼接的钩子有{hook_chars}字，本轮 rewritten_remainder 应为{max(0, planned_minimum-hook_chars)}-{max(0, maximum-hook_chars)}字。\n"
                    f'【写作前字数与信息覆盖规划】\n{budget}\n'
                    '字数偏差仅指长度，表达需要深度重构。不要重复输出锁定钩子。\n'
                    f'【锁定钩子，程序逐字拼接】\n{hook}\n\n【可改写正文，包含结尾】\n{source_body}'
                    + feedback
                )}], temperature=0.7, max_tokens=config.REWRITE_MAX_TOKENS,
                response_format={'type': 'json_object'},
            )
        except Exception as exc:
            history[-1]['state'] = 'service_error'
            history[-1]['issues'] = ['改写请求失败，保留已有稿及已使用次数']
            if checkpoint:
                checkpoint(history)
            if last is None:
                if attempt == MAX_REVISIONS or 'model_not_found' in str(exc).lower():
                    raise
                continue
            stop_reason = 'service_error'
            if attempt == MAX_REVISIONS or 'model_not_found' in str(exc).lower():
                break
            continue
        choice = response.choices[0]
        raw = (choice.message.content or '').strip()
        try:
            obj = json.loads(raw)
        except (ValueError, TypeError):
            obj = {}
        body = str(obj.get('rewritten_remainder') or '').strip() if isinstance(obj, dict) else ''
        if body:
            # The fixed prefix is assembled in code, not entrusted to the model.
            body = remainder(body, hook) if body.startswith(hook) else body
            text = hook + '\n\n' + format_for_reading(body)
            candidates = [text]
        else:
            candidates = _parse_candidates(raw)
            text = candidates[0] if len(candidates) == 1 else ''
        if not text:
            last_issues = ['未返回完整JSON正文，请返回 rewritten_remainder 字段']
            history[-1] = {'attempt': attempt + 1, 'revision': attempt, 'issues': last_issues, 'text': '', 'state':'invalid'}
            if checkpoint:
                checkpoint(history)
            continue
        structure = _rewrite_structure(raw, text)
        similarity = review_rewrite(source, text, hook)
        issues = _candidate_issues(candidates, source, getattr(choice, 'finish_reason', None),
                                   mode, context['category'], 'single') + similarity['retry_issues']
        if effective_length(text) < planned_minimum:
            issues.append(f'未达到95%写作目标：当前{effective_length(text)}字，至少{planned_minimum}字')
        missing_terms = [term for term in protected_terms(source) if term not in text]
        if missing_terms:
            issues.append('未原样保留书名或数字：' + '、'.join(missing_terms))
        issues = list(dict.fromkeys(issues))
        skill_audit = audit_output(source, text, obj) if skill_profile else None
        if skill_audit:
            issues = list(dict.fromkeys(issues + skill_audit['issues']))
        strategies = obj.get('rewrite_strategy', []) if isinstance(obj, dict) else []
        strategies = [s.strip()[:240] for s in strategies if isinstance(s, str) and s.strip()][:5] if isinstance(strategies, list) else []
        entry = {'attempt': attempt + 1, 'revision': attempt, 'text': text,
                 'generation_seconds': round(time.monotonic() - request_started, 3),
                 'strategy': strategies, 'issues': issues, 'similarity': similarity,
                 'complete': getattr(choice, 'finish_reason', None) != 'length'}
        if skill_audit:
            entry['skill_audit'] = skill_audit
        history[-1] = entry
        actual_tail = text.split('\n\n')[-1]
        structure.update({
            'hook': hook, 'hook_text': hook, 'hook_strategy': 'preserved',
            'body_text': remainder(text, hook), 'tail_text': actual_tail,
            'paragraphs': [p for p in text.split('\n\n') if p.strip()],
            'source_text': source, 'source_formatted': format_for_reading(source),
            'complete': getattr(choice, 'finish_reason', None) != 'length',
            'quality_warnings': issues,
        })
        if skill_audit:
            structure['rewrite_skill'] = {**skill_profile, **skill_audit}
        if checkpoint:
            entry['structure'] = json.loads(json.dumps(structure))
            checkpoint(history)
        # A later revision can regress; hand over the best usable draft at the cap.
        rank = attempt_rank(entry)
        if best_rank is None or rank < best_rank:
            last = (candidates, [_text_len(text)], structure)
            selected_attempt = attempt + 1
            best_rank = rank
        last_issues = issues
        if not issues:
            stop_reason = 'locked_hook_floor' if similarity['status'] != 'passed' else 'passed'
            break
    if last is None:
        raise ValueError('改写服务连续未返回可用正文，请稍后重试')
    candidates, lengths, structure = last
    selected = next(entry for entry in history if entry['attempt'] == selected_attempt)
    final_report = dict(selected['similarity'])
    planning_warnings = [issue for issue in selected['issues'] if issue.startswith('未达到95%写作目标')]
    delivery_issues = [issue for issue in selected['issues'] if issue not in planning_warnings]
    if delivery_issues:
        final_report['status'] = 'manual_review'
    structure['rewrite_review'] = {
        **final_report, 'max_revisions': MAX_REVISIONS,
        'planned_min_chars': planned_minimum, 'planning_warnings': planning_warnings,
        'revisions_used': len(history) - 1, 'selected_attempt': selected_attempt,
        'stop_reason': stop_reason, 'attempts': [{key:value for key,value in item.items() if key != 'structure'} for item in history],
        'strategy': selected['strategy'], 'issues': delivery_issues,
        'rewrite_skill': structure.get('rewrite_skill'),
        'comparison_summary': [
            f"开头锁定 {effective_length(hook)} 个有效字符，生成稿由程序原样拼接。",
            f"原稿 {final_report['source_chars']} 字，交付稿 {final_report['candidate_chars']} 字，偏差 {final_report['length_deviation']:+.1%}（不计标点与空白）。",
            f"首次有效稿正文重复指标 {next(e['similarity']['unlocked']['score'] for e in history if e.get('similarity')):.1%}，交付稿 {final_report['unlocked']['score']:.1%}。",
        ],
    }
    return candidates, lengths, structure


def _generate_candidates(
    source: str,
    context: dict[str, str],
    rewrite_notes: str = "",
    mode: str = "initial_dedup",
    narration_mode: str = "single",
) -> tuple[list[str], list[int], dict]:
    if narration_mode != "dual_dialogue":
        return _generate_single_candidates(source, context, rewrite_notes, mode)
    source_len = _text_len(source)
    prompt_kind = _rewrite_prompt_kind(context["category"], mode, narration_mode)
    prompt = load_prompt(context["category"], prompt_kind, use_shared=False)
    source_label = "首发版本最终确认稿" if mode == "repost_dedup" else "已清洗正文"
    tolerance_label = "10%" if context["category"] == "social_science" else ("8%" if mode == "repost_dedup" else "12%")
    terms = "、".join(protected_terms(source)) or "无额外词语"
    last_issues: list[str] = []
    attempts = 2 if context["category"] == "social_science" and narration_mode != "dual_dialogue" else 1
    for attempt in range(attempts):
        correction = ""
        if attempt:
            correction = "\n上一次输出不合格：" + "；".join(last_issues) + "。请完整重写并严格输出 JSON。"
            if narration_mode == "dual_dialogue":
                correction += (
                    "每轮正文控制在 12 到 70 字，绝不能超过 90 字；长回答必须拆成主持人追问和嘉宾续答。"
                    "角色标签不计入正文长度。保持原文开头钩子的核心反差、结尾核心语义、全部事实和书名，"
                    "只调整问答组织，不得新增原文没有的事实。"
                )
        if narration_mode == "dual_dialogue":
            temperature = (0.55, 0.40, 0.25)[attempt]
        else:
            temperature = 0.35 if mode == "repost_dedup" else 0.7
        history_pacing = (
            "统一深度二创规则：开头和结尾锁定，中段实质重构。改写后的正文必须尽量使用短句。较长句子在自然语义停顿处补逗号，"
            "每个口播分句尽量控制在10-12个汉字以内；不得删减原文信息，不得把一句话机械切碎。"
            "中段必须做实质性重构，可使用信息顺序重组、叙事视角转换、主动被动转换、句式重写和同等强度细节替换；"
            "保留原文五感描写、情绪强度和核心共鸣句，禁止空洞套话、AI腔和简单同义词替换。"
            if narration_mode != "dual_dialogue" else ""
        )
        resp = _request_rewrite(
            model=config.REWRITE_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        f"主题关键词：{context['keyword']}\n"
                        f"原视频标题：{context['title']}\n"
                        f"原作者标识：{context['author']}\n"
                        f"补充要求：{rewrite_notes or '无'}\n"
                        f"{history_pacing}\n"
                        f"必须原样保留的词：{terms}\n"
                        "统一规则：CTA 不生成、不改写、不追加；书名只读取原文明确出现的内容，否则 book_title 为空且 book_title_source=absent。\n"
                        f"原文有效字数约 {source_len} 字。目标差异控制在 {tolerance_label} 以内。"
                        + (
                            f"双人播客必须保留开头钩子核心语义，可参考原文前 120 字：{source[:120]}；"
                            f"结尾收束可参考原文后 120 字：{source[-120:]}。"
                            if narration_mode == "dual_dialogue" else ""
                        )
                        + f"{correction}\n\n待处理的{source_label}：\n{source}"
                    ),
                },
            ],
            temperature=temperature,
            max_tokens=config.REWRITE_MAX_TOKENS if narration_mode == "dual_dialogue" else None,
            response_format={"type": "json_object"},
        )
        choice = resp.choices[0]
        raw = (choice.message.content or "").strip()
        candidates = _parse_candidates(raw)
        structure = _rewrite_structure(raw, candidates[0]) if candidates else {}
        last_issues = _candidate_issues(
            candidates, source, getattr(choice, "finish_reason", None), mode, context["category"], narration_mode
        )
        if narration_mode == "dual_dialogue" and not structure.get("delivery_plan"):
            last_issues.append("双人播客未输出与对话稿一致的逐轮语气指令")
        if candidates:
            structure["quality_warnings"] = last_issues + _candidate_warnings(
                candidates[0], source, mode, context["category"], narration_mode
            )
            hard_length_issue = context["category"] == "social_science" and any(
                issue.startswith("改写稿过短") or issue.startswith("改写稿明显超出")
                for issue in last_issues
            )
            if not hard_length_issue or attempt == attempts - 1:
                if hard_length_issue:
                    raise ValueError("历史社科类改写未满足全文与原稿相差不超过10%的长度约束")
                return (candidates, [_text_len(text) for text in candidates], structure)
    raise ValueError("改写模型未返回可解析的正文")


def _find_clean(task_id: str) -> str | None:
    res = (
        db.get_client().table("artifacts")
        .select("storage_path")
        .eq("task_id", task_id)
        .eq("type", "clean")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0]["storage_path"] if res.data else None


def _load_clean_text(task_id: str) -> str:
    stage_res = (
        db.get_client().table("stages")
        .select("params")
        .eq("task_id", task_id)
        .eq("kind", "clean")
        .limit(1)
        .execute()
    )
    stage_data = stage_res.data if isinstance(stage_res.data, list) else []
    params = (stage_data[0].get("params") or {}) if stage_data and isinstance(stage_data[0], dict) else {}
    if isinstance(params, dict) and params.get("manual_clean_confirmed") and params.get("manual_clean_text"):
        return str(params["manual_clean_text"]).strip()

    cl_path = _find_clean(task_id)
    if not cl_path:
        return ""
    local = storage.download_artifact(cl_path, ".json")
    try:
        cleaned = json.load(open(local, encoding="utf-8"))
        return str(cleaned.get("cleaned") or cleaned.get("raw", "")).strip()
    finally:
        try:
            os.remove(local)
        except OSError:
            pass


def _task_context(task_id: str, source: str) -> dict[str, str]:
    task = db.get_task_prompt_context(task_id)
    category = normalize_category(task.get("content_category"))
    title = str(task.get("title") or "")
    return {
        "category": category,
        "title": title,
        "author": author_name(task.get("author")),
        "keyword": derive_keyword(title, source),
        "rewrite_mode": str(task.get("rewrite_mode") or "initial_dedup"),
        "source_task_id": str(task.get("source_task_id") or ""),
    }


def _load_final_text(task_id: str) -> str:
    res = (
        db.get_client().table("artifacts")
        .select("storage_path")
        .eq("task_id", task_id)
        .eq("type", "rewrite")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return ""
    local = storage.download_artifact(res.data[0]["storage_path"], ".json")
    try:
        payload = json.load(open(local, encoding="utf-8"))
        return str(payload.get("final_text") or "").strip()
    finally:
        try:
            os.remove(local)
        except OSError:
            pass


def _upload_rewrite(path: str, payload: dict) -> None:
    storage.upload_bytes(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        "application/json",
    )


def run(stage: dict) -> tuple[str, str | None]:
    task_id = stage["task_id"]
    # A reviewer can confirm while a worker is polling. Reload the stage
    # instead of relying on the pre-claim snapshot returned by PostgREST.
    latest = db.retry(
        lambda: db.get_client().table("stages")
        .select("params")
        .eq("id", stage["id"])
        .single()
        .execute()
    ).data or {}
    params = latest.get("params") or stage.get("params") or {}
    if params.get('input_mode') == 'ready_script':
        from ready_script import materialize
        imported = db.get_client().table('stages').select('params').eq('task_id', task_id).eq('kind', 'ingest').single().execute().data or {}
        return 'done', materialize({'task_id': task_id, 'params': imported.get('params') or {}})
    chosen = params.get("chosen_index")
    task_context = db.get_task_prompt_context(task_id)
    mode = str(task_context.get("rewrite_mode") or params.get("rewrite_mode") or "initial_dedup")
    source_task_id = str(task_context.get("source_task_id") or params.get("source_task_id") or "")
    source = _load_final_text(source_task_id) if mode == "repost_dedup" else _load_clean_text(task_id)
    if not source:
        message = "未找到首发最终文案（源任务改写阶段未完成）" if mode == "repost_dedup" else "未找到清洗产物（clean 未完成？）"
        db.set_stage(stage["id"], "failed", error=message)
        return "failed", None
    context = _task_context(task_id, source)
    if params.get('content_line') and params['content_line'] != context['category']:
        db.set_stage(stage['id'], 'needs_review', error='任务内容类型与二创规则快照不一致，请检查任务设置')
        return 'needs_review', None
    narration_mode = str(params.get("narration_mode") or "single")
    if chosen is None and narration_mode != 'dual_dialogue':
        template_rows = db.get_client().table('stages').select('params').eq('task_id',task_id).in_('kind',['image','render']).execute().data or []
        templates = [(row.get('params') or {}).get('production_template') for row in template_rows]
        try:
            context['rewrite_skill'] = resolve_domain(source, params.get('rewrite_domain','auto'), [item for item in templates if item], context['category'])
        except DomainConflict as exc:
            db.set_stage(stage['id'],'needs_review',error=str(exc))
            return 'needs_review', None

    if chosen is not None:
        res = (
            db.get_client().table("artifacts")
            .select("storage_path")
            .eq("task_id", task_id)
            .eq("type", "rewrite")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            sp = res.data[0]["storage_path"]
            local = storage.download_artifact(sp, ".json")
            try:
                with open(local, encoding="utf-8") as handle:
                    rw = json.load(handle)
                candidates = rw.get("candidates", [])
                idx = int(chosen)
                if idx < 0 or idx >= len(candidates):
                    raise ValueError("改写稿不存在")
                final_text = str(params.get("final_text") or candidates[idx]).strip()
                if not final_text:
                    raise ValueError("最终文案不能为空")
                if rw.get('rewrite_review'):
                    original_source = rw.get('source_text') or source
                    minimum, _maximum = length_bounds(original_source)
                    if effective_length(final_text) < minimum:
                        message = f'文稿不得减少超过15%：原稿{effective_length(original_source)}字，至少{minimum}字，当前{effective_length(final_text)}字。请补回原有信息后确认。'
                        rw['manual_draft'] = {'index': idx, 'text': final_text}
                        _upload_rewrite(sp, rw)
                        restored_params = {key: value for key, value in params.items() if key not in ('chosen_index', 'final_text')}
                        db.get_client().table('stages').update({'status':'needs_review', 'error':message,
                            'params':restored_params, 'output_ref':sp}).eq('id',stage['id']).execute()
                        return 'needs_review', sp
                    rw.pop('manual_draft', None)
                rw.update({
                    "chosen": idx,
                    "final_text": final_text,
                    "final_length": _text_len(final_text),
                })
                if rw.get('rewrite_review'):
                    original_source = rw.get('source_text') or source
                    rw['final_similarity'] = review_rewrite(original_source, final_text, rw.get('hook_text') or opening_hook(original_source))
                    rw['final_similarity']['issues'] = rw['final_similarity']['retry_issues']
                    rw['final_similarity']['stop_reason'] = 'manual_confirmed'
                if context["category"] == "social_science":
                    rw["cover_title"] = str(params.get("cover_title") or "").strip()
                    rw["cover_subtitle"] = str(params.get("cover_subtitle") or "").strip()
                    rw["cover_confirmed"] = params.get("cover_confirmed") is True
                plan = rw.get("delivery_plan")
                if (
                    str(task_context.get("narration_mode") or params.get("narration_mode") or "single") == "dual_dialogue"
                    and final_text == str(candidates[idx]).strip()
                    and isinstance(plan, list)
                ):
                    rw["final_delivery_plan"] = plan
                else:
                    rw.pop("final_delivery_plan", None)
                _upload_rewrite(sp, rw)
            finally:
                try:
                    os.remove(local)
                except OSError:
                    pass
            db.get_client().table("stages").update({"error": None}).eq("id", stage["id"]).execute()
            return "done", sp

    rewrite_notes = str(params.get("rewrite_notes") or "").strip()
    if narration_mode == "dual_dialogue":
        rewrite_notes = (rewrite_notes + "\n改为双人播客对话：每段以“主持人：”或“嘉宾：”开头，嘉宾可连续展开；保留事实边界，首段仍须有反差、反常识或悬念钩子。不要增加角色设定以外的事实。 ").strip()
    checkpoint = None
    if context.get('rewrite_skill'):
        from rewrite_checkpoint import prepare
        _extension, context['rewrite_skill'] = prompt_extension(context['rewrite_skill'])
        context['rewrite_skill']['base_prompt_sha256'] = hashlib.sha256(load_prompt(context['category'], 'initial_dedup').encode()).hexdigest()
        resumed, checkpoint = prepare(stage, params, source, context['rewrite_skill'], rewrite_notes, mode)
        context['rewrite_resume'], context['rewrite_checkpoint'] = resumed, checkpoint
    candidates, lengths, structure = _generate_candidates(
        source,
        context,
        rewrite_notes,
        mode,
        narration_mode,
    )
    context.pop('rewrite_checkpoint', None)
    context.pop('rewrite_resume', None)
    report = compliance.check_text(
        _llm(), config.REWRITE_MODEL, context["category"], candidates[0], context
    )
    payload = {
        "candidates": candidates,
        "styles": [mode],
        "candidate_lengths": lengths,
        "source_length": _text_len(source),
        "complete": True,
        "chosen": None,
        "final_text": None,
        "content_category": context["category"],
        "rewrite_mode": mode,
        "narration_mode": narration_mode,
        "delivery_plan": structure.get("delivery_plan"),
        "source_task_id": source_task_id or None,
        "compliance": report,
        **structure,
    }
    sp = f"{task_id}/rewrite/{uuid.uuid4()}.json"
    _upload_rewrite(sp, payload)
    if checkpoint:
        checkpoint(checkpoint.last_history, 'finished')
    storage.add_artifact(task_id, "rewrite", "rewrite", sp, meta={
        "candidate_count": len(candidates),
        "candidate_lengths": lengths,
        "source_length": payload["source_length"],
        "source_effective_chars": effective_length(source),
        "rewrite_mode": mode,
        "source_task_id": source_task_id or None,
        "model": config.REWRITE_MODEL,
        "complete": payload["complete"],
        "content_category": context["category"],
        "compliance_status": report["status"],
        "hook_strategy": structure["hook_strategy"],
        "cover_options": structure.get('cover_options', []),
        "review_status": (structure.get('rewrite_review') or {}).get('status'),
        "prompt_version": 'book_skill_v1.2.0' if context.get('rewrite_skill') else ('deep_rewrite_v2' if narration_mode != 'dual_dialogue' else 'dialogue_existing'),
        "rewrite_domain": (structure.get('rewrite_skill') or {}).get('domain'),
        "skill_version": (structure.get('rewrite_skill') or {}).get('version'),
        "skill_rules_sha256": (structure.get('rewrite_skill') or {}).get('rules_sha256'),
    })
    db.get_client().table("stages").update({
        "status": "needs_review",
        "output_ref": sp,
        "error": "存在高风险合规项，请修改后重新确认" if report["status"] == "blocked" else (
            "自动二创检查未全部达标，请查看对照与返工记录后人工确认"
            if (structure.get('rewrite_review') or {}).get('status') == 'manual_review' else None),
    }).eq("id", stage["id"]).execute()
    return "needs_review", sp
