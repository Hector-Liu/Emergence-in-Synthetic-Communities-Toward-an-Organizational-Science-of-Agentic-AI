"""Call count and cost estimate shown before every paid run (SPEC 9.1).

Token numbers are assumptions until a smoke run measures them; the page shows a range.
"""
from __future__ import annotations

from .config import RunConfig
from .llm import price_for

# output tokens per call (thinking included), by effort: rough central guesses
OUTPUT_BY_EFFORT = {"low": 300, "medium": 800, "high": 1800, "xhigh": 3000, "max": 4500}
WRITE_RATE = 0.75  # share of visits that write something
POSTS_PER_VISIT = 0.3
NAV_OUTPUT_SHARE = 0.6  # step 1 of a two-step visit thinks less than step 2 (a guess until measured)
SECONDS_PER_CALL = 6.8  # measured in pilot-1 (Haiku 5.5, effort high)


def estimate(cfg: RunConfig, measured: dict | None = None) -> dict:
    """measured: optional {"input_per_call": x, "output_per_call": y} from a smoke run."""
    fc = cfg.feed
    two_step = cfg.visit.two_step and cfg.boards_on()
    nav_in = 0.0
    feed_size = fc.new + fc.hot + fc.random + fc.random_seeded + fc.other_hot * max(0, len(cfg.communities) - 1)
    n_comments = fc.comments_per_post if fc.comments_per_post is not None else \
        fc.comments_new + fc.comments_top + fc.comments_random
    per_post = 150 + 90 * n_comments  # tokens: header, title and body, then about 90 per comment shown
    visits_by_model: dict[str, int] = {}
    tokens_in = 0.0
    active: list[tuple[str, int]] = []  # (model, joined_round)
    posts = 0.0
    r = 0
    for p in cfg.phases:
        for g in p.add:
            active += [(g.model, r + 1)] * g.n
        for _ in range(p.rounds):
            r += 1
            shown = 0 if cfg.switches.solo else min(feed_size, posts)
            act = cfg.visit_rate()  # expected share of agents visiting this round
            if r == 1 and cfg.opening_visitors() is not None:
                act = cfg.opening_visitors() / max(1, len(active))
            for model, joined in active:
                own = WRITE_RATE * (r - joined) * act
                memory = 0 if cfg.switches.memory == "off" else min(own, cfg.memory.recent_full) * 110 + \
                    max(0.0, own - cfg.memory.recent_full) * 40
                tokens_in += act * (300 + shown * per_post + 100 + memory)
                if two_step:  # step 1: board list, replies, record
                    nav_in += act * (400 + 60 * 4 + memory)
                visits_by_model[model] = visits_by_model.get(model, 0) + act
            posts += POSTS_PER_VISIT * len(active) * act
    visits = round(sum(visits_by_model.values()))
    steps = 2 if two_step else 1
    calls = visits * steps * 1.05  # about 5% retries
    out_per_call = OUTPUT_BY_EFFORT[cfg.llm.effort]
    in_per_call = tokens_in / visits if visits else 0
    nav_in_per = nav_in / visits if visits else 0
    nav_effort = cfg.llm.effort if cfg.visit.nav_effort == "same" else cfg.visit.nav_effort
    nav_out = OUTPUT_BY_EFFORT[nav_effort] * NAV_OUTPUT_SHARE
    if measured:
        in_per_call = measured.get("input_per_call", in_per_call)
        out_per_call = measured.get("output_per_call", out_per_call)
    cost_mid, unknown = 0.0, []
    for model, n in visits_by_model.items():
        price = price_for(model)
        if price is None:
            unknown.append(model)
            continue
        cost_mid += n * 1.05 * (in_per_call * price[0] + out_per_call * price[1]) / 1e6
        if two_step:
            cost_mid += n * 1.05 * (nav_in_per * price[0] + nav_out * price[1]) / 1e6
    # run time: calls in a visit go one after another; visits overlap up to the window (sequential) or up to
    # the concurrency limit within a round (simultaneous)
    per_round = visits / max(1, cfg.total_rounds())
    parallel = cfg.order.overlap if cfg.order.mode == "sequential" else max(1.0, min(cfg.llm.concurrency, per_round))
    minutes = calls * SECONDS_PER_CALL / parallel / 60
    return {"visits": visits, "calls": round(calls), "input_per_call": round(in_per_call), "minutes": round(minutes),
            "output_per_call": out_per_call, "cost_low": round(cost_mid * 0.6, 3), "cost_mid": round(cost_mid, 3),
            "cost_high": round(cost_mid * 1.7, 3), "unknown_prices": unknown,
            "basis": f"output measured in smoke run {measured.get('from_run', '')}" if measured else "assumed; a smoke run measures it"}
