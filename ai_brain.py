import json
from dotenv import load_dotenv
load_dotenv()  # Must run before initializing ChatOpenAI

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from bot_logger import log_error, log_info

# ── Model Configuration ───────────────────────────────────────────────────────
# To reduce cost in future: set MODEL_DECISION = "gpt-4o-mini"
# Stage 1 (pre-screen) always uses mini — runs every 5-min cycle, very cheap.
# Stage 2 (deep analysis) uses the decision model — only fires on promising setups.
MODEL_PRESCREEN = "gpt-4o-mini"   # cheap gate — never change this
MODEL_DECISION  = "gpt-4o"        # ← switch to "gpt-4o-mini" to cut costs

llm_mini = ChatOpenAI(model=MODEL_PRESCREEN, temperature=0.1)
llm_pro  = ChatOpenAI(model=MODEL_DECISION,  temperature=0.05)


# ── Trade Decision: Stage 1 (Pre-Screen) ─────────────────────────────────────

_PRESCREEN_TEMPLATE = """You are a strict quantitative trading pre-screener. 
Your ONLY job is to score the current setup on a 0-100 scale and recommend whether it 
deserves a full deep analysis. You do NOT trade — you just score.

CURRENT MARKET STATE (enriched):
{state}

Score each of the following dimensions (0 = failing, 1 = passing):

MACRO_SCORE (0 or 1):
  - 1D trend is clearly Bullish or Bearish (not ranging), AND
  - ADX > 25 (trend has real strength)

MOMENTUM_SCORE (0 or 1):
  - 1H MACD histogram is non-zero AND its direction aligns with 1D trend, AND
  - 1H RSI is between 40-70 (not exhausted, not over-extended)

MICRO_SCORE (0 or 1):
  - 5m RSI is not in extreme territory against the trade direction (not >75 for LONG entry, not <25 for SHORT entry), AND
  - Volume ratio >= 1.0 (participation is present)

VETO CONDITIONS (any = immediate HOLD):
  - 1D trend is Bearish AND planning a LONG
  - 1D trend is Bullish AND planning a SHORT
  - ADX < 15 (no trend at all)
  - RSI Divergence detected (unless specifically trading reversals)
  - Volume ratio < 0.5 (dead volume, fakeout risk)

OUTPUT STRICT JSON ONLY:
{{"macro_score": 0_or_1, "momentum_score": 0_or_1, "micro_score": 0_or_1, "total": 0_to_3, "veto": true_or_false, "veto_reason": "string_or_null", "proceed_to_deep_analysis": true_or_false, "preliminary_bias": "LONG|SHORT|HOLD"}}

RULES: proceed_to_deep_analysis = true ONLY when total >= 2 AND veto == false.
"""

# ── Trade Decision: Stage 2 (Deep Analysis) ──────────────────────────────────

_DEEP_ANALYSIS_TEMPLATE = """You are a veteran quantitative crypto hedge fund manager with 20 years of experience.
You have passed the pre-screen. Now perform deep analysis to produce a precise, actionable trade decision.

═══════════════════════════════════════
 LIVE MARKET DATA (Multi-Timeframe)
═══════════════════════════════════════
{state}

═══════════════════════════════════════
 TEXTBOOK KNOWLEDGE (from 8 trading books)
═══════════════════════════════════════
{theory}

INSTRUCTION: Scan the book references above. Identify which pattern or strategy DIRECTLY applies 
to the current setup (cite the Book Ref number). If no pattern applies, say so explicitly.

═══════════════════════════════════════
 PAST EXPERIENCE (your own trade history)
═══════════════════════════════════════
{experience}

INSTRUCTION: Check your past trades above. Did similar setups historically WIN or LOSS? 
How does that adjust your confidence?

═══════════════════════════════════════
 PRE-SCREEN RESULT
═══════════════════════════════════════
{prescreen}

═══════════════════════════════════════
 CHAIN-OF-THOUGHT ANALYSIS PROTOCOL
═══════════════════════════════════════
Work through each step explicitly before giving the final JSON:

STEP 1 — MACRO ALIGNMENT:
  State the 1D trend and ADX. Is the trend tradeable? 
  Does the planned direction ({preliminary_bias}) align with the macro trend?

STEP 2 — MOMENTUM CONFIRMATION:
  State the 1H MACD cross, histogram value, and momentum (accelerating/decelerating).
  State the 1H RSI. Does momentum support entry right now or is it exhausted?

STEP 3 — MICRO ENTRY TIMING:
  State the 5m RSI, Bollinger Band position, and volume ratio.
  Is there a precise entry trigger (RSI pullback, BB bounce, volume surge)?
  Note the swing high ({swing_high}) and swing low ({swing_low}) as context for S/R.

STEP 4 — THEORY SYNTHESIS:
  Which book reference best matches this setup? Quote 1 sentence from it.
  If none match, state "No direct book reference — relying on technical signals only."

STEP 5 — EXPERIENCE SYNTHESIS:
  Did any past experience warn against or support this trade?
  Quote the most relevant lesson. Adjust confidence accordingly.

STEP 6 — RISK MANAGEMENT:
  The market suggests SL distance = {sl_distance} (1.5× ATR) and TP distance = {tp_distance} (3.0× ATR).
  Compute entry_price, stop_loss, and take_profit using these distances from current price {current_price}.
  Ensure Risk:Reward >= 2:1 always.

STEP 7 — FINAL DECISION:
  Based on steps 1-6, output the final JSON decision.
  If ANY major conflict exists between steps (e.g. strong macro but exhausted momentum), 
  choose HOLD and explain why.

═══════════════════════════════════════
 FINAL OUTPUT (STRICT JSON, NO MARKDOWN)
═══════════════════════════════════════
{{
  "action": "LONG" | "SHORT" | "HOLD",
  "confidence": <integer 0-100>,
  "entry_price": <float>,
  "stop_loss": <float>,
  "take_profit": <float>,
  "risk_reward_ratio": <float>,
  "theory_cited": "<Book Ref N: one-sentence quote or 'None'>",
  "experience_cited": "<brief summary of most relevant past lesson or 'None'>",
  "reasoning": "<2-3 sentence summary covering macro, momentum, micro, and why this is the right time>"
}}
"""

# ── Reflection ────────────────────────────────────────────────────────────────

_REFLECTION_TEMPLATE = """You are an algorithmic trading auditor. Evaluate this closed position and extract a reusable lesson.

TRADE CONTEXT:
{trade}

FINAL OUTCOME: {outcome}

Write a structured lesson following this EXACT format:
LESSON: [1-sentence core rule to apply in future trades]
SIGNALS_THAT_WORKED: [what indicators correctly predicted the move]
SIGNALS_THAT_FAILED: [what indicators were misleading]
MARKET_REGIME: [describe the market state at entry: e.g. "Bullish Strong ADX 32, MACD Accelerating"]
IMPROVEMENT: [1 concrete change to make next time]

Be specific about indicator values. Do NOT write generic lessons like "the market was volatile."
"""


def _parse_json(raw_text: str, label: str):
    """Strips markdown fencing and parses JSON, with detailed error logging."""
    cleaned = raw_text.replace("```json", "").replace("```", "").strip()
    # Remove chain-of-thought before final JSON block
    if "{" in cleaned:
        cleaned = cleaned[cleaned.rfind("{"):]   # take last JSON object
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        log_error(f"[AI ERROR] Failed to parse {label} JSON: {e}\nRaw: {raw_text[:300]}", send_tg=True)
        return None


def generate_trade_decision(market_state: dict, theory_context: str, experience_context: str):
    """
    Two-stage decision pipeline:
    Stage 1: gpt-4o-mini pre-screens the setup cheaply (runs every 5min cycle).
    Stage 2: gpt-4o performs deep chain-of-thought analysis ONLY when setup passes pre-screen.
    
    Returns the full decision dict, or None on failure.
    """
    state_json = json.dumps(market_state, indent=2)

    # ── Stage 1: Pre-screen ───────────────────────────────────────────────────
    log_info("[BRAIN] Stage 1: Running pre-screen...", send_tg=False)
    prescreen_prompt = PromptTemplate(
        input_variables=["state"],
        template=_PRESCREEN_TEMPLATE
    )
    prescreen_response = llm_mini.invoke(prescreen_prompt.format(state=state_json))
    prescreen = _parse_json(prescreen_response.content, "prescreen")

    if not prescreen:
        log_error("[BRAIN] Pre-screen JSON parse failed.", send_tg=True)
        return None

    log_info(
        f"[BRAIN] Pre-screen → Total: {prescreen.get('total')}/3 | "
        f"Veto: {prescreen.get('veto')} | Bias: {prescreen.get('preliminary_bias')}",
        send_tg=False
    )

    if prescreen.get("veto"):
        log_info(f"[BRAIN] VETO triggered: {prescreen.get('veto_reason')} → HOLD", send_tg=False)
        return {
            "action": "HOLD",
            "confidence": 0,
            "entry_price": market_state.get("current_price", 0),
            "stop_loss": 0,
            "take_profit": 0,
            "risk_reward_ratio": 0,
            "theory_cited": "None",
            "experience_cited": "None",
            "reasoning": f"Veto: {prescreen.get('veto_reason', 'Setup does not meet minimum criteria.')}"
        }

    if not prescreen.get("proceed_to_deep_analysis"):
        log_info(
            f"[BRAIN] Setup score {prescreen.get('total')}/3 — below threshold. HOLD.",
            send_tg=False
        )
        return {
            "action": "HOLD",
            "confidence": 0,
            "entry_price": market_state.get("current_price", 0),
            "stop_loss": 0,
            "take_profit": 0,
            "risk_reward_ratio": 0,
            "theory_cited": "None",
            "experience_cited": "None",
            "reasoning": f"Pre-screen score {prescreen.get('total')}/3 — insufficient signal alignment."
        }

    # ── Stage 2: Deep analysis (gpt-4o) ──────────────────────────────────────
    log_info("[BRAIN] Stage 2: Running deep analysis with gpt-4o...", send_tg=False)
    risk = market_state.get("risk_sizing", {})
    micro = market_state.get("micro_5m", {})

    deep_prompt = PromptTemplate(
        input_variables=["state", "theory", "experience", "prescreen",
                         "preliminary_bias", "swing_high", "swing_low",
                         "sl_distance", "tp_distance", "current_price"],
        template=_DEEP_ANALYSIS_TEMPLATE
    )
    deep_response = llm_pro.invoke(deep_prompt.format(
        state=state_json,
        theory=theory_context,
        experience=experience_context,
        prescreen=json.dumps(prescreen),
        preliminary_bias=prescreen.get("preliminary_bias", "HOLD"),
        swing_high=micro.get("swing_high_30c", "N/A"),
        swing_low=micro.get("swing_low_30c", "N/A"),
        sl_distance=risk.get("suggested_sl_distance", "N/A"),
        tp_distance=risk.get("suggested_tp_distance", "N/A"),
        current_price=market_state.get("current_price", 0)
    ))

    decision = _parse_json(deep_response.content, "deep analysis")
    if decision:
        # Ensure RR is always computed and recorded
        entry = decision.get("entry_price", 0)
        sl    = decision.get("stop_loss", 0)
        tp    = decision.get("take_profit", 0)
        if entry and sl and tp and abs(entry - sl) > 0:
            rr = round(abs(tp - entry) / abs(entry - sl), 2)
            decision["risk_reward_ratio"] = rr

    return decision


def generate_reflection(trade_context: dict, outcome: str) -> str:
    """
    Evaluates a closed trade and extracts a rich, structured lesson.
    Returns the raw lesson string (validated before saving by memory_manager).
    """
    prompt = PromptTemplate(
        input_variables=["trade", "outcome"],
        template=_REFLECTION_TEMPLATE
    )
    response = llm_pro.invoke(prompt.format(
        trade=json.dumps(trade_context, indent=2),
        outcome=outcome
    ))
    return response.content.strip()