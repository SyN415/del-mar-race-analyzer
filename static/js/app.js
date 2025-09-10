// Del Mar Race Analysis Application - Main JavaScript

// Global application state
const App = {
    currentSession: null,
    pollInterval: null,
    isDebugMode: false
};

// Utility functions
const Utils = {
    // Format date for display
    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
    },

    // Format duration in seconds to human readable
    formatDuration(seconds) {
        if (seconds < 60) {
            return `${seconds.toFixed(1)}s`;
        } else if (seconds < 3600) {
            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = Math.floor(seconds % 60);
            return `${minutes}m ${remainingSeconds}s`;
        } else {
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            return `${hours}h ${minutes}m`;
        }
    },

    // Show toast notification
    showToast(message, type = 'info') {
        // Create toast element if it doesn't exist
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
            toastContainer.style.zIndex = '9999';
            document.body.appendChild(toastContainer);
        }

        const toastId = 'toast-' + Date.now();
        const toastHtml = `
            <div id="${toastId}" class="toast align-items-center text-white bg-${type} border-0" role="alert">
                <div class="d-flex">
                    <div class="toast-body">
                        ${message}
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                </div>
            </div>
        `;

        toastContainer.insertAdjacentHTML('beforeend', toastHtml);
        const toastElement = document.getElementById(toastId);
        const toast = new bootstrap.Toast(toastElement, { delay: 5000 });
        toast.show();

        // Remove toast element after it's hidden
        toastElement.addEventListener('hidden.bs.toast', () => {
            toastElement.remove();
        });
    },

    // Show loading spinner
    showLoading(message = 'Loading...') {
        let loadingOverlay = document.getElementById('loading-overlay');
        if (!loadingOverlay) {
            loadingOverlay = document.createElement('div');
            loadingOverlay.id = 'loading-overlay';
            loadingOverlay.className = 'loading-overlay';
            loadingOverlay.innerHTML = `
                <div class="text-center">
                    <div class="spinner-border spinner-border-lg text-primary mb-3" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <div class="h5 text-primary">${message}</div>
                </div>
            `;
            document.body.appendChild(loadingOverlay);
        }
        loadingOverlay.style.display = 'flex';
    },

    // Hide loading spinner
    hideLoading() {
        const loadingOverlay = document.getElementById('loading-overlay');
        if (loadingOverlay) {
            loadingOverlay.style.display = 'none';
        }
    },

    // API request wrapper
    async apiRequest(url, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
            },
        };

        const mergedOptions = { ...defaultOptions, ...options };
        
        try {
            const response = await fetch(url, mergedOptions);
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('API Request failed:', error);
            throw error;
        }
    }
};

// Analysis management
const Analysis = {
    // Start new analysis
    async start(formData) {
        try {
            Utils.showLoading('Starting analysis...');
            
            const response = await Utils.apiRequest('/api/analyze', {
                method: 'POST',
                body: JSON.stringify(formData)
            });
            
            App.currentSession = response.session_id;
            Utils.hideLoading();
            
            // Redirect to progress page
            window.location.href = `/progress/${response.session_id}`;
            
        } catch (error) {
            Utils.hideLoading();
            Utils.showToast(`Failed to start analysis: ${error.message}`, 'danger');
            throw error;
        }
    },

    // Get analysis status
    async getStatus(sessionId) {
        try {
            return await Utils.apiRequest(`/api/status/${sessionId}`);
        } catch (error) {
            console.error('Failed to get analysis status:', error);
            throw error;
        }
    },

    // Poll analysis status with AI enhancement tracking
    startPolling(sessionId, callback, interval = 2000) {
        if (App.pollInterval) {
            clearInterval(App.pollInterval);
        }

        const poll = async () => {
            try {
                const status = await this.getStatus(sessionId);

                // Enhanced callback with AI status
                callback(status);

                // Update AI service status indicators
                this.updateAIStatus(status);

                // Stop polling if complete or failed
                if (status.status === 'completed' || status.status === 'failed') {
                    this.stopPolling();
                }
            } catch (error) {
                console.error('Polling error:', error);
                callback({ error: error.message });
            }
        };

        // Start polling immediately, then at intervals
        poll();
        App.pollInterval = setInterval(poll, interval);
    },

    // Update AI service status indicators
    updateAIStatus(status) {
        // Update AI status badge
        const aiStatusBadge = document.getElementById('ai-status-badge');
        if (aiStatusBadge) {
            if (status.stage && status.stage.includes('ai')) {
                aiStatusBadge.innerHTML = '<i class="fas fa-robot me-1"></i>AI Active';
                aiStatusBadge.className = 'badge bg-warning text-dark ms-2';
            } else if (status.status === 'completed') {
                aiStatusBadge.innerHTML = '<i class="fas fa-robot me-1"></i>AI Complete';
                aiStatusBadge.className = 'badge bg-success ms-2';
            }
        }

        // Update individual AI service status
        const services = ['openrouter', 'scraping-assistant', 'analysis-enhancer'];
        services.forEach(service => {
            const statusElement = document.getElementById(`${service}-status`);
            if (statusElement) {
                if (status.stage && status.stage.includes(service.replace('-', '_'))) {
                    statusElement.textContent = 'Active';
                    statusElement.className = 'badge bg-warning';
                } else if (status.status === 'completed') {
                    statusElement.textContent = 'Complete';
                    statusElement.className = 'badge bg-success';
                }
            }
        });

        // Show AI insights preview if available
        if (status.ai_insights && status.ai_insights.length > 0) {
            const aiInsightsPreview = document.getElementById('ai-insights-preview');
            const aiInsightsContent = document.getElementById('ai-insights-content');

            if (aiInsightsPreview && aiInsightsContent) {
                aiInsightsPreview.style.display = 'block';
                aiInsightsContent.innerHTML = status.ai_insights.slice(0, 3).map(insight =>
                    `<div class="small mb-1">• ${insight}</div>`
                ).join('');
            }
        }
    },

        // Initial poll
        poll();
        
        // Set up interval
        App.pollInterval = setInterval(poll, interval);
        
        // Auto-stop after 10 minutes
        setTimeout(() => {
            if (App.pollInterval) {
                this.stopPolling();
                console.log('Polling stopped due to timeout');
            }
        }, 600000);
    },

    // Stop polling
    stopPolling() {
        if (App.pollInterval) {
            clearInterval(App.pollInterval);
            App.pollInterval = null;
        }
    }
};

// UI helpers
const UI = {
    // Update progress bar
    updateProgressBar(elementId, progress) {
        const progressBar = document.getElementById(elementId);
        if (progressBar) {
            progressBar.style.width = `${progress}%`;
            progressBar.setAttribute('aria-valuenow', progress);
            
            // Add animation classes
            if (progress === 100) {
                progressBar.classList.remove('progress-bar-animated');
                progressBar.classList.add('bg-success');
            }
        }
    },

    // Update step indicator
    updateStepIndicator(stepId, status) {
        const element = document.getElementById(stepId);
        if (!element) return;

        const icon = element.querySelector('i');
        if (!icon) return;

        // Reset classes
        icon.className = 'fas me-2';

        switch (status) {
            case 'pending':
                icon.classList.add('fa-circle', 'text-muted');
                break;
            case 'active':
                icon.classList.add('fa-spinner', 'fa-spin', 'text-primary');
                break;
            case 'completed':
                icon.classList.add('fa-check-circle', 'text-success');
                break;
            case 'failed':
                icon.classList.add('fa-times-circle', 'text-danger');
                break;
        }
    },

    // Animate element
    animateElement(element, animationClass) {
        if (typeof element === 'string') {
            element = document.getElementById(element);
        }
        
        if (element) {
            element.classList.add(animationClass);
            element.addEventListener('animationend', () => {
                element.classList.remove(animationClass);
            }, { once: true });
        }
    },

    // Format horse prediction for display
    formatHorsePrediction(prediction, rank) {
        const rankClass = rank === 1 ? 'top-pick' : rank === 2 ? 'second-pick' : rank === 3 ? 'third-pick' : '';
        const rankIcon = rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : rank;

        return `
            <div class="horse-prediction ${rankClass} p-3 mb-2 rounded">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <span class="me-2">${rankIcon}</span>
                        <strong>${prediction.horse_name || 'Unknown'}</strong>
                        <span class="text-muted ms-2">#${prediction.post_position || 'N/A'}</span>
                    </div>
                    <div class="text-end">
                        <div class="badge bg-primary">${(prediction.composite_rating || 0).toFixed(1)}</div>
                        <div class="small text-muted">${(prediction.win_probability || 0).toFixed(1)}%</div>
                    </div>
                </div>
                <div class="mt-2 small text-muted">
                    J: ${prediction.jockey || 'N/A'} | T: ${prediction.trainer || 'N/A'}
                </div>
            </div>
        `;
    },

    // Generate AI confidence visualization
    generateConfidenceChart(confidenceData) {
        if (!confidenceData) return '';

        const horses = Object.keys(confidenceData).slice(0, 5); // Top 5 horses

        return `
            <div class="ai-confidence-chart mb-3">
                <h6 class="text-muted mb-3">
                    <i class="fas fa-chart-bar me-1"></i>
                    AI Confidence Analysis
                </h6>
                ${horses.map(horse => {
                    const data = confidenceData[horse];
                    const score = (data.score * 100).toFixed(0);
                    const level = data.level;
                    const color = level === 'very_high' ? 'success' :
                                 level === 'high' ? 'primary' :
                                 level === 'moderate' ? 'warning' : 'secondary';

                    return `
                        <div class="d-flex align-items-center mb-2">
                            <div class="flex-shrink-0" style="width: 120px;">
                                <small class="text-muted">${horse}</small>
                            </div>
                            <div class="flex-grow-1 mx-2">
                                <div class="progress" style="height: 8px;">
                                    <div class="progress-bar bg-${color}"
                                         style="width: ${score}%"></div>
                                </div>
                            </div>
                            <div class="flex-shrink-0">
                                <small class="text-${color}">${score}%</small>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    },

    // Generate value opportunities display
    generateValueOpportunities(valueOpportunities) {
        if (!valueOpportunities || valueOpportunities.length === 0) return '';

        return `
            <div class="value-opportunities mb-3">
                <h6 class="text-success mb-3">
                    <i class="fas fa-gem me-1"></i>
                    AI Value Opportunities
                </h6>
                ${valueOpportunities.slice(0, 3).map(opportunity => `
                    <div class="card border-success mb-2">
                        <div class="card-body py-2">
                            <div class="d-flex justify-content-between align-items-center">
                                <div>
                                    <strong class="text-success">${opportunity.horse}</strong>
                                    <div class="small text-muted">${opportunity.reasoning}</div>
                                </div>
                                <div class="text-end">
                                    <span class="badge bg-success">Value: ${opportunity.value_score?.toFixed(2) || 'High'}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }
};

// Event handlers
const EventHandlers = {
    // Handle form submissions
    handleAnalysisForm(event) {
        event.preventDefault();
        
        const formData = new FormData(event.target);
        const data = Object.fromEntries(formData);
        
        // Validate form data
        if (!data.date || !data.llm_model) {
            Utils.showToast('Please fill in all required fields', 'warning');
            return;
        }
        
        // Start analysis
        Analysis.start(data).catch(error => {
            console.error('Analysis start failed:', error);
        });
    },

    // Handle page navigation
    handleNavigation(event) {
        const target = event.target.closest('[data-navigate]');
        if (target) {
            event.preventDefault();
            const url = target.getAttribute('data-navigate');
            window.location.href = url;
        }
    }
};

// Application initialization
document.addEventListener('DOMContentLoaded', function() {
    console.log('Del Mar Race Analysis Application initialized');
    
    // Set up global event listeners
    document.addEventListener('click', EventHandlers.handleNavigation);
    
    // Initialize analysis form if present
    const analysisForm = document.getElementById('analysisForm');
    if (analysisForm) {
        analysisForm.addEventListener('submit', EventHandlers.handleAnalysisForm);
    }
    
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Add fade-in animation to main content
    const mainContent = document.querySelector('main');
    if (mainContent) {
        mainContent.classList.add('fade-in');
    }
    
    // Debug mode check
    if (window.location.search.includes('debug=true')) {
        App.isDebugMode = true;
        console.log('Debug mode enabled');
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    Analysis.stopPolling();
});

// Export for global access
window.App = App;
window.Utils = Utils;
window.Analysis = Analysis;
window.UI = UI;
