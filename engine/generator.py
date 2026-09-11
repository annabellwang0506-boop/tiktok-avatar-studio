# -*- coding: utf-8 -*-
"""脚本内容引擎：钩子/正文/CTA/标题/标签/发布时段 —— 面向北美市场的英文内容生成。
LLM 可用时走 LLM，否则回退到模板化生成，保证离线也能跑通全流程。
"""
import re, time

HOOK_STYLES = [
    "curiosity",      # 好奇心缺口
    "bold_claim",     # 大胆断言
    "listicle",       # 数字清单
    "mistake",        # 反常识误区
    "story_open",     # 故事开局
    "question",       # 反问问句
    "pov",            # POV 视角
    "stop_doing",     # 立刻停止
]

FORMATS = [
    "listicle",       # 清单式
    "how_to",         # 教学式
    "myth_bust",      # 辟谣式
    "story",          # 故事式
    "comparison",     # 对比式
    "motivation",     # 激励式
    "behind_scenes",  # 幕后式
]

# ---- 最佳发布时间（美东时区，行业经验值启发式）--------------
BEST_TIMES = {
    "Monday":    ["07:00", "09:00", "11:30", "19:00", "21:00", "22:30"],
    "Tuesday":   ["07:00", "08:30", "12:00", "19:30", "21:00"],
    "Wednesday": ["07:30", "12:00", "19:00", "21:30"],
    "Thursday":  ["07:00", "11:30", "19:00", "22:00"],
    "Friday":    ["07:00", "09:00", "13:00", "19:00", "23:00"],
    "Saturday":  ["09:00", "10:30", "12:00", "20:00"],
    "Sunday":    ["09:00", "19:00", "20:30", "21:30"],
}

NICHE_TAGS = {
    "fitness":   ["#fitness", "#gymtok", "#workoutmotivation", "#fitnesstips", "#homeworkout", "#fatloss", "#musclebuilding", "#fitnesshacks", "#cardio", "#healthylifestyle"],
    "finance":   ["#personalfinance", "#moneytok", "#investing", "#passiveincome", "#budgeting", "#wealthbuilding", "#financetips", "#sidehustle", "#stockmarket", "#financialfreedom"],
    "beauty":    ["#beautytok", "#makeuptutorial", "#skincare", "#hairtok", "#grwm", "#beautyhacks", "#selfcare", "#glowup", "#beautyproducts", "#nails"],
    "food":      ["#foodtok", "#recipes", "#easyrecipes", "#cooking", "#mealprep", "#comfortfood", "#foodiefinds", "#quickrecipes", "#healthyfood", "#asmr"],
    "tech":      ["#tech", "#artificialintelligence", "#ai", "#technews", "#futuretech", "#coding", "#aigadgets", "#smartphone", "#startup", "#viraldigital"],
    "motivation":["#motivation", "#mindset", "#selfimprovement", "#discipline", "#success", "#productivity", "#morningroutine", "#hustle", "#grind", "#personaldevelopment"],
    "pet":       ["#pets", "#dogsoftiktok", "#catsoftiktok", "#petsoftiktok", "#animals", "#puppy", "#kitten", "#funnydogs", "#petlovers", "#cuteanimals"],
    "travel":    ["#travel", "#traveltok", "#hiddengems", "#travelhacks", "#bucketlist", "#wanderlust", "#vacation", "#roadtrip", "#solotravel", "#usa"],
    "business":  ["#smallbusiness", "#entrepreneur", "#businesstips", "#marketing", "#ecommerce", "#sales", "#startup", "#sidehustle", "#branding", "#socialmediamarketing"],
    "default":   ["#fyp", "#viral", "#trending", "#tiktok", "#learnontiktok", "#usa", "#america", "#howto", "#tutorial", "#hacks"],
}

CTA_TEMPLATES = [
    "If this helped, drop a follow for more {niche} tips every week. And comment below — I read every single one.",
    "Follow me so you never miss the next one. Save this video for when you need it, and share it with someone who needs to see it.",
    "Which one of these are you doing {topic}? Tell me in the comments. Follow for part 2.",
    "Tap follow — I post new {niche} insights every single day. Turn on notifications so you don't miss tomorrow's video.",
    "If you learned one thing, that's a win. Follow for more, and send this to a friend who's been doing it wrong.",
]


def _sample(pool):
    return pool[int(time.time() * 1000) % len(pool)]


def _clean(text):
    text = re.sub(r"\s+", " ", text).strip()
    return text


def hook_variants(topic, fmt, style, niche):
    """为同一主题生成 5 个钩子变体（默认风格或指定风格）。"""
    topic = topic.strip().rstrip("? .!")
    T = {
        "curiosity": [
            f"The #1 thing nobody tells you about {topic}",
            f"I wasn't expecting this about {topic} — and it changes everything",
            f"3 secrets about {topic} that took me years to learn",
        ],
        "bold_claim": [
            f"Stop doing {topic} the wrong way right now",
            f"Here's why most people fail at {topic} (and how you won't)",
            f"You're doing {topic} all wrong — here's the fix",
        ],
        "listicle": [
            f"5 {topic} tips that actually work",
            f"3 things I wish I knew before {topic}",
            f"7 mistakes to avoid when it comes to {topic}",
        ],
        "mistake": [
            f"The biggest myth about {topic} — debunked",
            f"Everything you've been told about {topic} is backwards",
            f"Stop believing this lie about {topic}",
        ],
        "story_open": [
            f"I almost gave up on {topic} — then this happened",
            f"Let me tell you what really happened with {topic}",
            f"Two years into {topic}, this changed my entire approach",
        ],
        "question": [
            f"Are you secretly making this {topic} mistake?",
            f"Would you bet on {topic} — most people get it wrong",
            f"How long until you get real results from {topic}?",
        ],
        "pov": [
            f"POV: you finally figured out {topic}",
            f"POV: someone just showed you the shortcut for {topic}",
            f"POV: it's your turn to master {topic}",
        ],
        "stop_doing": [
            f"Stop wasting months on {topic} — do this instead",
            f"Stop doing this one thing with {topic} today",
            f"Quit making these {topic} mistakes immediately",
        ],
    }
    pool = T.get(style, T["curiosity"])
    if style == "all" or style == "":
        # 全风格采样一个组合
        pool = []
        for s in HOOK_STYLES:
            pool.extend(T.get(s, []))
    variants = list(set(pool))
    return variants[:5]


_BODY_BY_FMT = {
    "listicle": [
        "Here's the exact breakdown. Number one: start with the smallest possible version of {topic} — consistency beats intensity every single time.",
        "Number two: track your progress weekly, not daily. What gets measured gets improved, and daily noise will only discourage you.",
        "Number three: copy the people who already get results — not the people who just talk about it. Model their routine, then tweak it for yourself.",
        "Number four: remove one obstacle that keeps blocking you. If you're not starting, the problem is the environment, not you.",
        "And number five: keep a 'done' list, not just a to-do list. Momentum is built on finished tasks, one after another.",
    ],
    "how_to": [
        "Let me walk you through it step by step. First, get crystal clear on your end goal — vague goals produce vague results.",
        "Second, break {topic} into one action you can finish in under 15 minutes today. Small wins compound fast.",
        "Third, schedule it like a non-negotiable appointment. Momentum comes from showing up, not from motivation.",
        "Fourth, review what worked at the end of each week and double down on it. Cut everything that isn't moving the needle.",
        "And fifth, share your progress publicly — it locks in accountability and brings opportunities you can't see yet.",
    ],
    "myth_bust": [
        "Let's bust this once and for all. The truth? Most of what you hear about {topic} comes from people trying to sell you something.",
        "Real results follow a boring pattern: clear goals, consistent action, and honest feedback loops. No shortcuts, no magic.",
        "The people who succeed aren't smarter — they just test faster and adjust sooner when something stops working.",
        "So stop chasing the next shiny trick. Pick one method, run it for 30 days, and let the data tell you the truth.",
    ],
    "story": [
        "Let me tell you a quick story. Months ago I was exactly where you are — overwhelmed, unsure, and honestly a little stuck on {topic}.",
        "So I did the uncomfortable thing: I asked someone who had already done it to show me where I was wasting time.",
        "The gap wasn't effort — it was direction. One honest conversation rearranged my entire plan.",
        "Within weeks the same hours started producing three times the results. Not because I worked harder, but because I worked smarter.",
        "And that's the whole message today: you don't need more hustle. You need better information, applied consistently.",
    ],
    "comparison": [
        "There are two ways to approach {topic}, and only one of them actually works long-term.",
        "The first way is all hype: chase motivation, switch methods every week, and blame bad luck when results stall.",
        "The second way is boring but proven: pick one system, commit to it for 90 days, measure weekly, and adjust only at the end of each cycle.",
        "Same effort, completely different outcomes. The difference is patience plus a feedback loop.",
        "Which one do you want for yourself? It's a choice, not a talent.",
    ],
    "motivation": [
        "Here's the truth nobody will say out loud: the only thing blocking you from real results on {topic} is the story you keep telling yourself.",
        "Read that again — your excuses are just unpracticed plans. Every specialist started as a beginner who refused to quit.",
        "You don't need permission, a perfect setup, or the right moment. You need action, repeated past the point where it stops being comfortable.",
        "Discipline will take you places motivation cannot. And it's built one boring, repeatable day at a time.",
        "Start today. Even one tiny step breaks the inertia — and momentum is the closest thing to magic you'll ever find.",
    ],
    "behind_scenes": [
        "Everyone shows you the highlight reel of {topic}. Here's what the process actually looks like behind the scenes.",
        "It's messier and slower than it looks online — failed attempts, boring repetition, and a hundred small decisions nobody sees.",
        "But that's exactly why it works: the people winning are simply the ones who kept showing up when no one was watching.",
        "So when you see someone succeeding on {topic}, remember the invisible reps. Then start your own.",
    ],
}


def build_script(avip, topic, fmt="listicle", hook_style="all"):
    """生成完整脚本包（英文，北美风格）。返回 dict。"""
    niche = avip.get("niche", "default")
    topic = _clean(topic)
    fmt = fmt if fmt in FORMATS else "listicle"
    hooks = hook_variants(topic, fmt, hook_style, niche)
    hook = hooks[0]

    body = [b.format(topic=topic) for b in _BODY_BY_FMT[fmt]]
    cta = _sample(CTA_TEMPLATES).format(niche=niche, topic=topic)
    script_text = " ".join([hook + ".", *body, cta])
    script_text = _clean(script_text)

    word_count = len(script_text.split())
    duration_s = max(18, int(word_count / 2.4))  # 170wpm 语音速度估算

    tags = NICHE_TAGS.get(niche, NICHE_TAGS["default"])[:10] + ["#fyp", "#foryou", "#viral"]
    tags = list(dict.fromkeys(tags))
    caption = script_text.split(". ")[0] + " — " + " ".join(tags[:12])

    return {
        "avip_id": avip.get("id"),
        "topic": topic,
        "format": fmt,
        "hook_style": hook_style,
        "hook": hook,
        "hook_variants": hooks,
        "body_paragraphs": body,
        "cta": cta,
        "script_text": script_text,
        "word_count": word_count,
        "duration_seconds": duration_s,
        "caption": caption,
        "hashtags": tags,
        "language": avip.get("language", "en-US"),
    }


def llm_script(avip, topic, fmt, hook_style, base_url, api_key, model):
    """OpenAI 兼容接口生成（DeepSeek / OpenAI / Kimi / 通义 等均可），失败时返回 None。"""
    if not api_key:
        return None
    niche = avip.get("niche", "default")
    prompt = (
        f"You are a top TikTok content strategist for the US market. Write a {fmt} script "
        f"about: {topic}. Niche: {niche}. Tone: {avip.get('tone', 'energetic, direct')}.\n"
        f"Return JSON with fields: hook_variants (5 one-liner hooks, style {hook_style or 'mixed'}), "
        f"body_paragraphs (4-5 short spoken sentences each, natural spoken English), cta (one follow-worthy call to action), "
        f"script_text (the full spoken script, 110-160 words), caption (2-3 lines), hashtags (list of 12-20), duration_seconds (int)."
    )
    try:
        import requests
        r = requests.post(
            base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={"model": model,
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.8,
                  "response_format": {"type": "json_object"}},
            timeout=90,
        )
        r.raise_for_status()
        out = json_loads(r.json()["choices"][0]["message"]["content"])
        out["avip_id"] = avip.get("id")
        out["topic"] = topic
        out["format"] = fmt
        out["hook_style"] = hook_style
        out["language"] = avip.get("language", "en-US")
        return out
    except Exception:
        return None


def json_loads(s):
    import json
    try:
        return json.loads(s)
    except Exception:
        import re
        m = re.search(r"\{.*\}", s, re.S)
        return json.loads(m.group(0))


def schedule_slot(existing_keys):
    """从 BEST_TIMES 找一个未被占用的 ET 时段（美东）。"""
    import datetime
    used = set(existing_keys or [])
    for day_offset in range(0, 7):
        d = datetime.date.today() + datetime.timedelta(days=day_offset)
        day_name = d.strftime("%A")
        for t in BEST_TIMES.get(day_name, []):
            key = f"{d.isoformat()} {t}"
            if key not in used:
                return {"date": d.isoformat(), "time_et": t, "key": key}
    return {"date": (datetime.date.today() + datetime.timedelta(days=7)).isoformat(),
            "time_et": "19:00", "key": ""}
