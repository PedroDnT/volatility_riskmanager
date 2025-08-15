#!/usr/bin/env python3
"""
Crypto Risk Management Web Application
=====================================
FastAPI-based web interface for the Advanced Crypto Position Risk Management System.
Provides real-time position analysis, volatility forecasting, and risk management recommendations.
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn

from position_risk_manager import PositionRiskManager

# Initialize FastAPI app
app = FastAPI(
    title="Crypto Risk Management Dashboard",
    description="Advanced cryptocurrency trading risk management system with real-time position monitoring and volatility analysis",
    version="1.0.0"
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Global risk manager instance
risk_manager = None
last_analysis = None
analysis_timestamp = None

# Pydantic models for API
class AnalysisRequest(BaseModel):
    sandbox: bool = False
    refresh: bool = False

class PositionData(BaseModel):
    symbol: str
    side: str
    size: float
    entry_price: float
    current_price: float
    pnl_pct: float
    leverage: float
    notional: float

async def get_risk_manager(sandbox: bool = False):
    """Get or create risk manager instance"""
    global risk_manager
    if risk_manager is None or risk_manager.sandbox != sandbox:
        risk_manager = PositionRiskManager(sandbox=sandbox)
    return risk_manager

async def run_analysis(sandbox: bool = False) -> Dict[str, Any]:
    """Run complete risk analysis"""
    global last_analysis, analysis_timestamp
    
    try:
        manager = await get_risk_manager(sandbox)
        
        # Fetch and analyze positions
        positions = manager.fetch_positions()
        
        if not positions:
            return {
                'success': False,
                'error': 'No positions found',
                'positions': [],
                'portfolio': {},
                'timestamp': datetime.utcnow().isoformat()
            }
        
        # Analyze all positions
        manager.analyze_all_positions()
        
        # Get portfolio metrics
        portfolio_metrics = manager._calculate_portfolio_metrics()
        
        # Format data for web interface
        formatted_positions = []
        for position in positions:
            symbol = position['symbol']
            analysis = manager.risk_analysis.get(symbol, {})
            
            formatted_positions.append({
                'symbol': symbol,
                'side': analysis.get('side', position.get('side', 'unknown')),
                'size': position.get('size', 0),
                'entry_price': analysis.get('entry_price', position.get('entryPrice', 0)),
                'current_price': analysis.get('current_price', analysis.get('live_price', 0)),
                'pnl_pct': analysis.get('pnl_pct', 0),
                'leverage': position.get('leverage', 1),
                'notional': position.get('notional', 0),
                'stop_loss': analysis.get('stop_loss', 0),
                'take_profit': analysis.get('take_profit', 0),
                'sl_pct_entry': analysis.get('sl_pct', 0),
                'tp_pct_entry': analysis.get('tp_pct', 0),
                'sl_pct_current': analysis.get('sl_pct_current', 0),
                'tp_pct_current': analysis.get('tp_pct_current', 0),
                'risk_reward_ratio': analysis.get('risk_reward_ratio', 0),
                'position_health': analysis.get('position_health', 'UNKNOWN'),
                'volatility': {
                    'method': analysis.get('volatility_method', 'N/A'),
                    'atr_pct': analysis.get('atr_pct_of_price', 0),
                    'har_sigma_ann': analysis.get('har_sigma_ann', 0),
                    'garch_sigma_ann': analysis.get('garch_sigma_ann', 0),
                    'blended_sigma_h': analysis.get('blended_sigma_h_pct', 0)
                },
                'risk_metrics': {
                    'optimal_size': analysis.get('optimal_size', 0),
                    'current_risk': analysis.get('current_risk_usd', 0),
                    'optimal_risk': analysis.get('optimal_risk_usd', 0),
                    'current_reward': analysis.get('current_reward_usd', 0),
                    'optimal_reward': analysis.get('optimal_reward_usd', 0)
                },
                'action_required': analysis.get('action_required', 'Set SL/TP as recommended'),
                'liquidation_price': analysis.get('approx_liq_price', 0),
                'anchor_price_used': analysis.get('anchor_price_used', 'current')
            })
        
        result = {
            'success': True,
            'positions': formatted_positions,
            'portfolio': portfolio_metrics,
            'timestamp': datetime.utcnow().isoformat(),
            'summary': {
                'total_positions': len(formatted_positions),
                'positions_at_risk': len(portfolio_metrics.get('positions_at_risk', [])),
                'total_notional': portfolio_metrics.get('total_notional', 0),
                'total_pnl': portfolio_metrics.get('total_unrealized_pnl', 0),
                'portfolio_risk_reward': portfolio_metrics.get('portfolio_risk_reward', 0)
            }
        }
        
        last_analysis = result
        analysis_timestamp = datetime.utcnow()
        
        return result
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'positions': [],
            'portfolio': {},
            'timestamp': datetime.utcnow().isoformat()
        }

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page"""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.post("/api/analyze")
async def analyze_positions(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """Run position analysis"""
    global last_analysis, analysis_timestamp
    
    # If we have recent analysis and refresh is not requested, return cached data
    if (not request.refresh and last_analysis and analysis_timestamp and 
        (datetime.utcnow() - analysis_timestamp).seconds < 300):  # 5 minutes cache
        return JSONResponse(content=last_analysis)
    
    # Run analysis in background for better UX
    if request.refresh:
        background_tasks.add_task(run_analysis, request.sandbox)
        return {"status": "analysis_started", "message": "Analysis started in background"}
    
    # Run analysis synchronously for immediate results
    result = await run_analysis(request.sandbox)
    return JSONResponse(content=result)

@app.get("/api/analysis/status")
async def get_analysis_status():
    """Get current analysis status"""
    global last_analysis, analysis_timestamp
    
    if last_analysis is None:
        return {"status": "no_analysis", "timestamp": None}
    
    return {
        "status": "available",
        "timestamp": analysis_timestamp.isoformat() if analysis_timestamp else None,
        "age_minutes": (datetime.utcnow() - analysis_timestamp).seconds // 60 if analysis_timestamp else None,
        "success": last_analysis.get('success', False),
        "summary": last_analysis.get('summary', {})
    }

@app.get("/api/analysis/latest")
async def get_latest_analysis():
    """Get the latest analysis results"""
    global last_analysis
    
    if last_analysis is None:
        raise HTTPException(status_code=404, detail="No analysis available")
    
    return JSONResponse(content=last_analysis)

@app.get("/api/positions")
async def get_positions():
    """Get formatted positions data"""
    global last_analysis
    
    if last_analysis is None:
        raise HTTPException(status_code=404, detail="No analysis available")
    
    return {"positions": last_analysis.get('positions', [])}

@app.get("/api/portfolio")
async def get_portfolio_metrics():
    """Get portfolio-level metrics"""
    global last_analysis
    
    if last_analysis is None:
        raise HTTPException(status_code=404, detail="No analysis available")
    
    return {"portfolio": last_analysis.get('portfolio', {})}

@app.post("/api/export")
async def export_analysis():
    """Export analysis to JSON"""
    global last_analysis
    
    if last_analysis is None:
        raise HTTPException(status_code=404, detail="No analysis available")
    
    # Create export filename with timestamp
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"risk_analysis_{timestamp}.json"
    
    try:
        with open(filename, 'w') as f:
            json.dump(last_analysis, f, indent=2, default=str)
        
        return {
            "success": True,
            "filename": filename,
            "message": f"Analysis exported to {filename}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

# Development server configuration
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=True if os.getenv("ENVIRONMENT") == "development" else False,

        limit_max_requests_jitter_backoff_factor=100,
    )
