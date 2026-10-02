import json
from dotenv import load_dotenv
load_dotenv()  # Must run before initializing ChatOpenAI

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

# Initialize the LLM (Lower temperature for analytical consistency)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)

def generate_trade_decision(market_state, theory_context, experience_context):
    """Synthesizes data and knowledge to output a JSON trade decision."""
    prompt = PromptTemplate(
        input_variables=["state", "theory", "experience"],
        template="""You are a quantitative crypto hedge fund manager. 
        
        Live Multi-Timeframe Data:
        {state}
        
        Textbook Theory:
        {theory}
        
        Your Past Experiences/Mistakes:
        {experience}
        
        Task: Output a strict JSON decision to LONG, SHORT, or HOLD. 
        CRITICAL: 
        1. Align trades with the 1D macro trend (Do not LONG if 1D is Bearish).
        2. Use the 5m Bollinger Bands and RSI for exact entry timing.
        3. Prioritize your Past Experiences over Textbook Theory.
        
        JSON Format:
        {{"action": "LONG"|"SHORT"|"HOLD", "confidence": 0-100, "entry_price": float, "stop_loss": float, "take_profit": float, "reasoning": "string"}}
        """
    )
    
    formatted_prompt = prompt.format(
        state=json.dumps(market_state, indent=2), 
        theory=theory_context, 
        experience=experience_context
    )
    
    response = llm.invoke(formatted_prompt)
    raw_text = response.content.replace("```json", "").replace("```", "").strip()
    
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        print("[AI ERROR] Failed to parse JSON.")
        return None

def generate_reflection(trade_context, outcome):
    """Evaluates a closed trade and extracts a reusable lesson."""
    prompt = PromptTemplate(
        input_variables=["trade", "outcome"],
        template="""You are an algorithmic trading auditor evaluating a closed position.
        
        Trade Context: {trade}
        Final Outcome: {outcome}
        
        Write a concise, 2-sentence actionable rule based on this outcome. 
        Start with 'LESSON:'. If it was a loss, explain the multi-timeframe misalignment.
        """
    )
    response = llm.invoke(prompt.format(trade=json.dumps(trade_context), outcome=outcome))
    return response.content.strip()