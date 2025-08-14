/**
 * Crypto Risk Management Dashboard JavaScript
 * Handles API interactions, UI updates, and user interactions
 */

class RiskDashboard {
    constructor() {
        this.isSandboxMode = false;
        this.currentAnalysis = null;
        this.isLoading = false;
        this.volatilityChart = null;
        
        this.initializeEventListeners();
        this.checkHealthAndLoadData();
        
        // Auto-refresh every 5 minutes
        setInterval(() => {
            if (!this.isLoading) {
                this.refreshAnalysis(false);
            }
        }, 300000);
    }
    
    initializeEventListeners() {
        // Refresh button
        document.getElementById('refresh-btn').addEventListener('click', () => {
            this.refreshAnalysis(true);
        });
        
        // Sandbox toggle
        document.getElementById('sandbox-toggle').addEventListener('click', () => {
            this.toggleSandboxMode();
        });
        
        // Export button
        document.getElementById('export-btn').addEventListener('click', () => {
            this.exportAnalysis();
        });
        
        // Modal close
        document.getElementById('close-modal').addEventListener('click', () => {
            this.closeModal();
        });
        
        // Close modal on background click
        document.getElementById('position-modal').addEventListener('click', (e) => {
            if (e.target.id === 'position-modal') {
                this.closeModal();
            }
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeModal();
            } else if (e.key === 'r' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                this.refreshAnalysis(true);
            }
        });
    }
    
    async checkHealthAndLoadData() {
        try {
            const response = await fetch('/api/health');
            if (response.ok) {
                this.updateStatus('connected', 'Connected');
                await this.loadAnalysis();
            } else {
                this.updateStatus('error', 'Server Error');
            }
        } catch (error) {
            console.error('Health check failed:', error);
            this.updateStatus('error', 'Connection Failed');
        }
    }
    
    async loadAnalysis() {
        try {
            const response = await fetch('/api/analysis/status');
            const status = await response.json();
            
            if (status.status === 'available') {
                const analysisResponse = await fetch('/api/analysis/latest');
                if (analysisResponse.ok) {
                    const analysis = await analysisResponse.json();
                    this.displayAnalysis(analysis);
                    return;
                }
            }
            
            // No analysis available, run new one
            await this.refreshAnalysis(false);
        } catch (error) {
            console.error('Failed to load analysis:', error);
            this.showError('Failed to load existing analysis');
            this.showState('error', 'Failed to load analysis. Check your API credentials and network connection.');
        }
    }
    
    async refreshAnalysis(force = false) {
        if (this.isLoading) return;
        
        this.isLoading = true;
        this.updateStatus('loading', 'Analyzing...');
        this.showState('loading');
        
        const refreshBtn = document.getElementById('refresh-btn');
        refreshBtn.classList.add('btn-loading');
        refreshBtn.disabled = true;
        
        try {
            const response = await fetch('/api/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    sandbox: this.isSandboxMode,
                    refresh: force
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.displayAnalysis(result);
                this.updateStatus('connected', 'Connected');
                this.showToast('Analysis completed successfully', 'success');
            } else {
                this.showError(result.error || 'Analysis failed');
                this.updateStatus('error', 'Analysis Failed');
            }
        } catch (error) {
            console.error('Analysis failed:', error);
            this.showError('Network error during analysis');
            this.updateStatus('error', 'Network Error');
        } finally {
            this.isLoading = false;
            refreshBtn.classList.remove('btn-loading');
            refreshBtn.disabled = false;
        }
    }
    
    toggleSandboxMode() {
        this.isSandboxMode = !this.isSandboxMode;
        const toggleBtn = document.getElementById('sandbox-toggle');
        
        if (this.isSandboxMode) {
            toggleBtn.classList.add('sandbox-active');
            toggleBtn.innerHTML = '<i class="fas fa-flask mr-2"></i>Sandbox ON';
            this.showToast('Sandbox mode enabled - using test data', 'warning');
        } else {
            toggleBtn.classList.remove('sandbox-active');
            toggleBtn.innerHTML = '<i class="fas fa-flask mr-2"></i>Sandbox';
            this.showToast('Live mode enabled - using real data', 'info');
        }
        
        // Refresh analysis with new mode
        setTimeout(() => {
            this.refreshAnalysis(true);
        }, 500);
    }
    
    displayAnalysis(analysis) {
        this.currentAnalysis = analysis;
        
        if (!analysis.success) {
            this.showError(analysis.error || 'Analysis failed');
            return;
        }
        
        if (!analysis.positions || analysis.positions.length === 0) {
            this.showState('error', 'No positions found. Make sure you have open positions in your account.');
            return;
        }
        
        // Update summary cards
        this.updateSummaryCards(analysis.summary);
        
        // Update positions table
        this.updatePositionsTable(analysis.positions);
        
        // Update volatility chart
        this.updateVolatilityChart(analysis.positions);
        
        // Update last update time
        const lastUpdate = new Date(analysis.timestamp);
        document.getElementById('last-update').textContent = 
            `Last updated: ${lastUpdate.toLocaleTimeString()}`;
        
        // Show main content
        this.showState('content');
    }
    
    updateSummaryCards(summary) {
        document.getElementById('total-positions').textContent = summary.total_positions || 0;
        document.getElementById('positions-at-risk').textContent = summary.positions_at_risk || 0;
        
        // Format PnL with color
        const pnlElement = document.getElementById('total-pnl');
        const totalPnl = summary.total_pnl || 0;
        pnlElement.textContent = this.formatCurrency(totalPnl);
        pnlElement.className = totalPnl >= 0 ? 'text-2xl font-bold pnl-positive' : 'text-2xl font-bold pnl-negative';
        
        // Format Risk:Reward ratio
        const rrRatio = summary.portfolio_risk_reward || 0;
        document.getElementById('portfolio-rr').textContent = `${rrRatio.toFixed(2)}:1`;
    }
    
    updatePositionsTable(positions) {
        const tbody = document.getElementById('positions-table-body');
        tbody.innerHTML = '';
        
        positions.forEach((position, index) => {
            const row = document.createElement('tr');
            row.className = 'table-row';
            row.addEventListener('click', () => this.showPositionDetails(position));
            
            const healthClass = this.getHealthClass(position.position_health);
            const sideClass = position.side.toLowerCase() === 'long' ? 'side-long' : 'side-short';
            const pnlClass = position.pnl_pct >= 0 ? 'pnl-positive' : 'pnl-negative';
            
            row.innerHTML = `
                <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">
                    ${position.symbol}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm ${sideClass}">
                    ${position.side.toUpperCase()}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                    $${this.formatNumber(position.entry_price)}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                    $${this.formatNumber(position.current_price)}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm ${pnlClass}">
                    ${this.formatPercent(position.pnl_pct)}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                    $${this.formatNumber(position.stop_loss)}
                    <div class="text-xs text-gray-500">
                        ${this.formatPercent(position.sl_pct_current)} from current
                    </div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                    $${this.formatNumber(position.take_profit)}
                    <div class="text-xs text-gray-500">
                        ${this.formatPercent(position.tp_pct_current)} from current
                    </div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                    ${position.risk_reward_ratio.toFixed(2)}:1
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                    <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${healthClass}">
                        ${position.position_health}
                    </span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm">
                    <button class="action-btn bg-blue-600 hover:bg-blue-700 text-white" 
                            onclick="event.stopPropagation(); dashboard.showPositionDetails(${JSON.stringify(position).replace(/"/g, '&quot;')})">
                        View
                    </button>
                </td>
            `;
            
            tbody.appendChild(row);
        });
    }
    
    updateVolatilityChart(positions) {
        const ctx = document.getElementById('volatility-chart').getContext('2d');
        
        // Destroy existing chart if exists
        if (this.volatilityChart) {
            this.volatilityChart.destroy();
        }
        
        const labels = positions.map(p => p.symbol);
        const atrData = positions.map(p => p.volatility.atr_pct);
        const garchData = positions.map(p => p.volatility.garch_sigma_ann);
        const harData = positions.map(p => p.volatility.har_sigma_ann);
        
        this.volatilityChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'ATR %',
                        data: atrData,
                        backgroundColor: 'rgba(59, 130, 246, 0.8)',
                        borderColor: 'rgba(59, 130, 246, 1)',
                        borderWidth: 1
                    },
                    {
                        label: 'GARCH σ (annual)',
                        data: garchData,
                        backgroundColor: 'rgba(245, 158, 11, 0.8)',
                        borderColor: 'rgba(245, 158, 11, 1)',
                        borderWidth: 1
                    },
                    {
                        label: 'HAR-RV σ (annual)',
                        data: harData,
                        backgroundColor: 'rgba(16, 185, 129, 0.8)',
                        borderColor: 'rgba(16, 185, 129, 1)',
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Volatility Models Comparison',
                        color: '#fff'
                    },
                    legend: {
                        labels: {
                            color: '#fff'
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            color: '#9CA3AF'
                        },
                        grid: {
                            color: 'rgba(75, 85, 99, 0.3)'
                        }
                    },
                    y: {
                        ticks: {
                            color: '#9CA3AF'
                        },
                        grid: {
                            color: 'rgba(75, 85, 99, 0.3)'
                        }
                    }
                }
            }
        });
    }
    
    showPositionDetails(position) {
        const modal = document.getElementById('position-modal');
        const modalTitle = document.getElementById('modal-title');
        const modalContent = document.getElementById('modal-content');
        
        modalTitle.textContent = `${position.symbol} - Position Details`;
        
        const healthClass = this.getHealthClass(position.position_health);
        const sideClass = position.side.toLowerCase() === 'long' ? 'side-long' : 'side-short';
        const pnlClass = position.pnl_pct >= 0 ? 'pnl-positive' : 'pnl-negative';
        
        modalContent.innerHTML = `
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <!-- Position Summary -->
                <div class="bg-gray-700 rounded-lg p-4">
                    <h4 class="text-lg font-semibold text-white mb-3">Position Summary</h4>
                    <div class="space-y-2 text-sm">
                        <div class="flex justify-between">
                            <span class="text-gray-300">Symbol:</span>
                            <span class="text-white font-medium">${position.symbol}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">Side:</span>
                            <span class="${sideClass}">${position.side.toUpperCase()}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">Size:</span>
                            <span class="text-white">${this.formatNumber(position.size)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">Leverage:</span>
                            <span class="text-white">${position.leverage}x</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">Notional:</span>
                            <span class="text-white">$${this.formatNumber(position.notional)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">Health:</span>
                            <span class="px-2 py-1 text-xs font-semibold rounded ${healthClass}">
                                ${position.position_health}
                            </span>
                        </div>
                    </div>
                </div>
                
                <!-- Price Information -->
                <div class="bg-gray-700 rounded-lg p-4">
                    <h4 class="text-lg font-semibold text-white mb-3">Price Information</h4>
                    <div class="space-y-2 text-sm">
                        <div class="flex justify-between">
                            <span class="text-gray-300">Entry Price:</span>
                            <span class="text-white">$${this.formatNumber(position.entry_price)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">Current Price:</span>
                            <span class="text-white">$${this.formatNumber(position.current_price)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">PnL:</span>
                            <span class="${pnlClass}">${this.formatPercent(position.pnl_pct)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">Liquidation Price:</span>
                            <span class="text-white">$${this.formatNumber(position.liquidation_price)}</span>
                        </div>
                    </div>
                </div>
                
                <!-- Risk Management -->
                <div class="bg-gray-700 rounded-lg p-4">
                    <h4 class="text-lg font-semibold text-white mb-3">Risk Management</h4>
                    <div class="space-y-2 text-sm">
                        <div class="flex justify-between">
                            <span class="text-gray-300">Stop Loss:</span>
                            <span class="text-white">$${this.formatNumber(position.stop_loss)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-500">SL % (from entry):</span>
                            <span class="text-gray-300">${this.formatPercent(position.sl_pct_entry)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-500">SL % (from current):</span>
                            <span class="text-gray-300">${this.formatPercent(position.sl_pct_current)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">Take Profit:</span>
                            <span class="text-white">$${this.formatNumber(position.take_profit)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-500">TP % (from entry):</span>
                            <span class="text-gray-300">${this.formatPercent(position.tp_pct_entry)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-500">TP % (from current):</span>
                            <span class="text-gray-300">${this.formatPercent(position.tp_pct_current)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">Risk:Reward:</span>
                            <span class="text-white">${position.risk_reward_ratio.toFixed(2)}:1</span>
                        </div>
                    </div>
                </div>
                
                <!-- Volatility Analysis -->
                <div class="bg-gray-700 rounded-lg p-4">
                    <h4 class="text-lg font-semibold text-white mb-3">Volatility Analysis</h4>
                    <div class="space-y-2 text-sm">
                        <div class="flex justify-between">
                            <span class="text-gray-300">Method:</span>
                            <span class="text-white">${position.volatility.method}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">ATR (% of price):</span>
                            <span class="text-white">${this.formatPercent(position.volatility.atr_pct)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">HAR-RV σ (annual):</span>
                            <span class="text-white">${this.formatPercent(position.volatility.har_sigma_ann)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">GARCH σ (annual):</span>
                            <span class="text-white">${this.formatPercent(position.volatility.garch_sigma_ann)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">Blended σ (4h):</span>
                            <span class="text-white">${this.formatPercent(position.volatility.blended_sigma_h)}</span>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Risk Metrics -->
            <div class="mt-6 bg-gray-700 rounded-lg p-4">
                <h4 class="text-lg font-semibold text-white mb-3">Risk Metrics</h4>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                    <div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">Optimal Size:</span>
                            <span class="text-white">${this.formatNumber(position.risk_metrics.optimal_size)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">Current Risk:</span>
                            <span class="text-white">$${this.formatNumber(position.risk_metrics.current_risk)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">Optimal Risk:</span>
                            <span class="text-white">$${this.formatNumber(position.risk_metrics.optimal_risk)}</span>
                        </div>
                    </div>
                    <div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">Current Reward:</span>
                            <span class="text-white">$${this.formatNumber(position.risk_metrics.current_reward)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">Optimal Reward:</span>
                            <span class="text-white">$${this.formatNumber(position.risk_metrics.optimal_reward)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-300">Anchor Price:</span>
                            <span class="text-white">${position.anchor_price_used}</span>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Action Required -->
            <div class="mt-4 bg-blue-900 border border-blue-600 rounded-lg p-4">
                <h4 class="text-lg font-semibold text-blue-300 mb-2">Recommended Action</h4>
                <p class="text-blue-200">${position.action_required}</p>
            </div>
        `;
        
        modal.classList.remove('hidden');
        modal.querySelector('.bg-gray-800').classList.add('modal-enter');
    }
    
    closeModal() {
        const modal = document.getElementById('position-modal');
        const modalDialog = modal.querySelector('.bg-gray-800');
        
        modalDialog.classList.remove('modal-enter');
        modalDialog.classList.add('modal-exit');
        
        setTimeout(() => {
            modal.classList.add('hidden');
            modalDialog.classList.remove('modal-exit');
        }, 300);
    }
    
    async exportAnalysis() {
        if (!this.currentAnalysis) {
            this.showToast('No analysis data to export', 'warning');
            return;
        }
        
        try {
            const response = await fetch('/api/export', {
                method: 'POST'
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showToast(`Analysis exported to ${result.filename}`, 'success');
            } else {
                this.showToast('Export failed', 'error');
            }
        } catch (error) {
            console.error('Export failed:', error);
            this.showToast('Export failed due to network error', 'error');
        }
    }
    
    showState(state, message = '') {
        const loadingState = document.getElementById('loading-state');
        const errorState = document.getElementById('error-state');
        const dashboardContent = document.getElementById('dashboard-content');
        
        // Hide all states
        loadingState.classList.add('hidden');
        errorState.classList.add('hidden');
        dashboardContent.classList.add('hidden');
        
        // Show requested state
        switch (state) {
            case 'loading':
                loadingState.classList.remove('hidden');
                break;
            case 'error':
                errorState.classList.remove('hidden');
                if (message) {
                    document.getElementById('error-message').textContent = message;
                }
                break;
            case 'content':
                dashboardContent.classList.remove('hidden');
                break;
        }
    }
    
    showError(message) {
        this.showState('error', message);
        this.showToast(message, 'error');
    }
    
    updateStatus(status, text) {
        const indicator = document.querySelector('#status-indicator .w-3');
        const statusText = document.getElementById('status-text');
        
        // Remove existing status classes
        indicator.classList.remove('status-connected', 'status-loading', 'status-error');
        
        // Add new status class
        indicator.classList.add(`status-${status}`);
        statusText.textContent = text;
    }
    
    showToast(message, type = 'info', duration = 5000) {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        
        const icons = {
            success: 'fas fa-check-circle',
            error: 'fas fa-exclamation-circle',
            warning: 'fas fa-exclamation-triangle',
            info: 'fas fa-info-circle'
        };
        
        toast.className = `toast toast-${type} flex items-center`;
        toast.innerHTML = `
            <i class="${icons[type]} mr-3"></i>
            <span>${message}</span>
            <button class="ml-auto text-white hover:text-gray-300" onclick="this.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        container.appendChild(toast);
        
        // Auto-remove after duration
        setTimeout(() => {
            if (toast.parentElement) {
                toast.remove();
            }
        }, duration);
    }
    
    getHealthClass(health) {
        const healthMap = {
            'CRITICAL': 'health-critical',
            'WARNING': 'health-warning', 
            'NORMAL': 'health-normal',
            'PROFITABLE': 'health-profitable',
            'UNKNOWN': 'health-unknown'
        };
        
        return healthMap[health] || 'health-unknown';
    }
    
    formatNumber(num, decimals = 4) {
        if (num === null || num === undefined || isNaN(num)) return '0.0000';
        return Number(num).toFixed(decimals);
    }
    
    formatPercent(num, decimals = 2) {
        if (num === null || num === undefined || isNaN(num)) return '0.00%';
        return `${(Number(num)).toFixed(decimals)}%`;
    }
    
    formatCurrency(num, decimals = 2) {
        if (num === null || num === undefined || isNaN(num)) return '$0.00';
        return `$${Number(num).toFixed(decimals)}`;
    }
}

// Initialize dashboard when DOM is loaded
let dashboard;
document.addEventListener('DOMContentLoaded', () => {
    dashboard = new RiskDashboard();
});

// Make dashboard globally available for onclick handlers
window.dashboard = dashboard;
