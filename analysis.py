import os, json, textwrap
from openai import OpenAI
from dotenv import load_dotenv

def load_report():
    """Load the report JSON file."""
    with open("risk_analysis.json", "r") as f:
        report = json.load(f)
    return report

def build_prompt(report):
    """Build the prompt by injecting the JSON."""
    return textwrap.dedent(
        f"""
        ROLE
        You are a crypto portfolio risk manager. You receive a JSON report (same shape as risk_analysis.json). Your job: recommend specific actions that (1) cut tail risk now, (2) avoid realizing losses unnecessarily, and (3) avoid getting stopped out too early, while keeping hard invalidations and portfolio discipline.

        WHAT TO RETURN
        - For each position, output either bullet points or a short paragraph (choose whichever is clearer for that position).
        - Also include a brief portfolio-level section at the top if useful.

        KEY DEFINITIONS
        - R (risk unit) = abs(entry − stop_loss) in price units.
        - Oversize ratio = current_size / optimal_size (if provided).
        - Premature stop risk: SL closer than ~2×ATR for swing entries.
        - No-hedge Risk-Freeze: lower effective leverage (by adding margin / switching to cross) and place reduce-only limit orders at/above breakeven; do not market-sell at a loss.
        - Time-stop: exit if price fails to reclaim entry within N bars (default N = 24 of the report’s timeframe).
        - Funding bleed = daily funding % × notional; cap acceptable bleed (default 0.20%/day).

        DECISION RULES
        1) Capital preservation first: never widen SL on an oversized loser unless you also lower effective leverage and pre-place reduce-only ladders. No martingale.
          2) Oversized & losing (oversize > 1.5×) → No-hedge Risk-Freeze:
    - Keep the report’s SL (hard invalidation).
    - Suggest ΔMargin_needed to target leverage ~6–10× on alts or push liq ≥ 3×ATR away.
    - Place reduce-only ladder:
      - p1 = entry (40%), p2 = entry + 0.5R (30%), p3 = TP1 (30%).
    - Add time-stop (24 bars).
    - If funding > 0.20%/day for 2 days while below entry → force partial via best ladder fill + cut remainder.
  3) Moderately oversized (1.1–1.5×): same ladder; ΔMargin optional.
  4) In profit: take partial at TP1 (or near), move SL to breakeven or start ATR trail (2×ATR; tighten to 1.5×ATR after 2R).
  5) Low R:R (<1.8): keep SL/TP; prefer lighten-on-bounce via ladders; don’t add.
  6) Near liquidation: prioritize ΔMargin to push liq beyond 3×ATR; otherwise exit on structure invalidation.
  7) Vol-model disagreement: prefer ATR/hybrid stops of 2–4× ATR to avoid premature stop-outs.
  8) Portfolio overlay: if several names are oversized/underwater and winners exist, trim a profitable correlated name (not a loser) to reduce portfolio beta/risk without crystallizing losses.

  FORMAT
  - Start with an optional Portfolio section (short bullets).
  - Then, for each position, include symbol and actions (bullets or a short paragraph).
  - Use the exact numbers from the JSON for SL/TP, entry, ladder levels (calculate entry + 0.5R where needed).
  - If any field is missing, skip that micro-action and note it briefly.
  - No chain-of-thought; provide conclusions only.

  INPUT JSON
  ```json {json.dumps(report, ensure_ascii=False)}```""",
)   

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def generate_response(prompt):
    """Generate a response using the OpenAI API."""
    resp = client.responses.create(
      model="gpt-5-mini",                   # use a current text model
      input=prompt,
      system="""
      You are a crypto portfolio risk manager. You receive a JSON report (same shape as risk_analysis.json). Your job: recommend specific actions that (1) cut tail risk now, (2) avoid realizing losses unnecessarily, and (3) avoid getting stopped out too early, while keeping hard invalidations and portfolio discipline.
        """,
      temperature=0.2,
      reasoning={"effort": "medium"}
  )

    return resp.output

def main():
    load_dotenv()
    # run the position_risk_manager.py file
    from position_risk_manager import position_risk_manager
    report = position_risk_manager.get_report()
    prompt = build_prompt(report)
    response = generate_response(prompt)
    print(response.output.text)
    with open("response.txt", "w") as f:
        f.write(response.output.text)
    print("Response saved to response.txt")
if __name__ == "__main__":
    main()              