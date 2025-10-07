# 🏇 Del Mar Race Analyzer - Production Ready

[![Deploy to Render](https://img.shields.io/badge/Deploy-Render-4A90E2)](https://render.com)
![Python Version](https://img.shields.io/badge/python-3.11-blue.svg)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Status](https://img.shields.io/badge/status-Production%20Ready-brightgreen)

**AI-Powered Horse Racing Scraper, Analyzer & Prediction Platform**

Transform racing data into profitable insights with advanced machine learning algorithms, sophisticated web scraping, and professional betting recommendations.

**Supported Tracks:** Del Mar (DMR) | Santa Anita (SA)

**🔧 Recent Updates:** SmartPick scraper fixed with Angular/JavaScript rendering support • Frontend CSS issues resolved • Enhanced debugging tools added

## 🚀 Features

### 🤖 **AI-Powered Analysis**
- **Multiple LLM Integration**: GPT-4o, Claude-3, and more via OpenRouter
- **Intelligent Scraping**: AI-guided page analysis and CAPTCHA navigation
- **Smart Predictions**: Advanced confidence scoring and risk assessment
- **Professional Recommendations**: Complete betting strategy analysis

### 📊 **Advanced Analytics**
- **6-Factor Prediction Engine**: Speed (25%), Class (15%), Form (20%), Workout (15%), Jockey (8%), Trainer (7%)
- **Multi-Track Support**: Del Mar (DMR) and Santa Anita (SA) with track-specific optimizations
- **Real-time Data**: Live horse stats, odds, and performance metrics from Equibase
- **Comprehensive Reports**: Professional-formatted analysis with betting recommendations

### 🦿 **Sophisticated Scraping**
- **Performance**: Top-tier scraping with anti-detection measures
- **Reliability**: Multi-layered fallback strategies for maximum uptime
- **Compliance**: Respectful rate limiting and user-agent rotation
- **Scale**: Handle complete race cards with parallel processing
- **Angular Support**: Fixed SmartPick scraper to handle JavaScript-rendered content
- **Enhanced Debugging**: Comprehensive debugging tools for troubleshooting

## 🏗️ Architecture

```
Horse Race Analyzer/
├── FastAPI Web Framework
├── SQLite Database (Production Ready)
├── Playwright Browser Automation
├── OpenRouter AI Integration (Claude Sonnet 4.5)
├── Advanced Prediction Engine
├── Multi-Track Support (DMR, SA)
└── Professional Web Interface
```

### 📁 **Project Structure**
```bash
del-mar-race-analyzer/
├── app.py                              # Main FastAPI application
├── race_prediction_engine.py          # Advanced prediction algorithms
├── scrapers/                          # Web scraping infrastructure
│   ├── playwright_equibase_scraper.py
│   ├── smartpick_playwright.py        # Fixed SmartPick scraper (Angular support)
│   └── fallback_scraper.py            # Backup scraper
├── services/                          # Business logic layer
│   ├── orchestration_service.py
│   ├── openrouter_client.py
│   ├── session_manager.py
│   └── captcha_solver.py              # 2Captcha integration
├── core/                              # Data models and utilities
│   └── horse_data.py
├── templates/                         # Jinja2 web templates
│   ├── base.html                      # Fixed with cache-busting
│   ├── landing.html
│   ├── progress.html
│   ├── results.html
│   └── error.html
├── static/                            # CSS, JS, images
│   ├── css/style.css                  # Fixed dark theme
│   └── js/app.js
├── config/                            # Configuration management
├── debug_output/                      # Debugging HTML files
├── render-deploy/                     # Production deployment
│   ├── render.yaml
│   └── Dockerfile
├── debug_smartpick_url.py             # SmartPick debugging tool
├── test_smartpick_urls_simple.py      # URL testing tool
├── smartpick_fix.py                   # SmartPick fix implementation
├── smartpick_scraper_patch.py         # Patch application tool
└── requirements.txt                   # Python dependencies
```

## 🚀 Quick Start

### **Local Development**
```bash
# Clone the repository
git clone https://github.com/your-username/del-mar-analyzer.git
cd del-mar-analyzer

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
python -m playwright install chromium

# Run the application
python app.py
# Access at http://localhost:8000
```

### **Production Deployment (Render.com)**
1. **Click Deploy**: [Deploy to Render](https://render.com)
2. **Configure Environment Variables**:
   - `OPENROUTER_API_KEY`: Your OpenRouter API key
   - `ENVIRONMENT`: production
   - `LOG_LEVEL`: INFO
3. **Deploy**: Application is live with full production features

## 🔧 Configuration

### **Environment Variables**
```bash
# Required
OPENROUTER_API_KEY=your_openrouter_api_key_here
TWOCAPTCHA_API_KEY=your_2captcha_api_key_here  # Required for SmartPick scraping

# Optional
ENVIRONMENT=production          # development/production
LOG_LEVEL=INFO                  # DEBUG/INFO/WARNING/ERROR
DATABASE_URL=sqlite:///./del_mar_analyzer.db
SCRAPER_HEADLESS=true           # false for debugging
SCRAPER_TIMEOUT=30              # scraping timeout in seconds
SECRET_KEY=your_secret_key      # for secure sessions
USE_FALLBACK_SCRAPER=false      # Use fallback if Playwright fails
```

### **Available AI Models**
- `gpt-4o` 🔥 **Recommended** (Best balance of speed/quality)
- `claude-3-sonnet` 🤖 (Excellent reasoning)
- `claude-3-haiku` ⚡ (Fastest responses)
- `gpt-4-turbo` 🚀 (High quality at good speed)
- `mistral-7b-instruct` 💰 (Cost-effective)

## 📊 API Reference

### **Start Analysis**
```bash
POST /api/analyze
Content-Type: application/json

{
  "date": "2025-09-15",
  "llm_model": "gpt-4o",
  "track_id": "DMR"
}

Response: Session ID for tracking progress
```

### **Check Analysis Status**
```bash
GET /api/status/{session_id}

Response: Current analysis progress and status
```

### **Health Check**
```bash
GET /health

Response: Service health and component status
```

## 🎯 Sample Output

```markdown
## 🏁 RACE 1 - 3:00 PM PT (836m, Dirt)
**Maiden Claiming $75K | 4YO+ | 6 Horses**

### 🎯 SmartPick Selection: #3 BRIGHT STAR ⭐⭐⭐⭐⭐

#### ✅ Prediction Confidence: 92%
```json
{
  "speed_score": 88,                    // Top speed rating
  "smartpick_combo_pct": 35,           // Jockey/trainer experience
  "workouts_quality": "Excellent",      // Recent training performance
  "trainer_win_pct": 28,               // Trainer success rate
  "jockey_win_pct": 21,                // Rider experience factor
  "class_rating": 82                   // Competition level assessment
}
```

#### 💰 **Betting Recommendation**
- **WIN BET**: #3 BRIGHT STAR (High Confidence)
- **EXACTA**: #3 over #6, #1, #5
- **Value Play**: #1 SEDONA STEEL (20% Discount)

#### 🎯 **Strategic Notes**
- Maintains excellent form with recent sharp workouts
- Benefited from class drop with solid last start recovery
- 35% combo win percentage suggests strong class fit
- Inside rail position provides tactical advantage
```

## 🔒 Security & Compliance

### **Data Protection**
- Respectful scraping with proper user-agent identification
- Rate limiting to prevent server strain
- No persistent identified data storage
- GDPR compliant data handling

### **API Security**
- Bearer token authentication
- Request validation and sanitization
- Input escaping and SQL injection prevention
- Secure environment variable management

### **Captcha Handling**
- **2Captcha Integration**: Automatic hCaptcha solving for SmartPick pages
- **Incapsula/Imperva Detection**: Handles WAF challenges gracefully
- **Fallback Strategies**: Multiple extraction methods for reliability

## 🧪 Testing & Debugging

### **SmartPick Scraper Testing**
```bash
# Test SmartPick URL construction and content
python debug_smartpick_url.py SA 09/28/2024 1

# Simple URL testing without Playwright
python test_smartpick_urls_simple.py SA 09/28/2024 1

# Apply SmartPick fixes if needed
python smartpick_scraper_patch.py
```

### **Unit Testing**
```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run the test suite
pytest tests/ -v

# Run coverage report
pytest --cov=del_mar_analyzer tests/
```

### **Debugging Tools**
- **HTML Output**: Debug files saved to `debug_output/` directory
- **Enhanced Logging**: Detailed scraping progress and error reporting
- **Screenshot Capture**: Visual debugging for SmartPick pages
- **URL Testing**: Multiple URL format validation

## 📈 Future Roadmap

### **Phase 4: Advanced Analytics (Q4 2025)**
- Historical performance tracking
- Cross-track pattern analysis
- Machine learning model improvements
- Real-time odds integration

### **Phase 5: Enterprise Features (Q1 2026)**
- Multi-user collaboration
- Custom model training
- Advanced reporting dashboard
- API for third-party integrations

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and add tests
4. Run the test suite: `pytest`
5. Commit your changes: `git commit -am 'Add feature'`
6. Push to the branch: `git push origin feature-name`
7. Create a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Original Development Team**: For the sophisticated scraping and analysis infrastructure
- **OpenRouter**: Enabling access to premium AI models
- **Render.com**: Providing excellent deployment platform
- **Equibase**: Source of horse racing data
- **FastAPI**: Modern Python web framework

## 🛠️ Troubleshooting

### **Common Issues & Solutions**

#### SmartPick Scraper Not Working
1. **Check 2Captcha API Key**: Ensure `TWOCAPTCHA_API_KEY` is set and has balance
2. **Use Past Dates**: Equibase doesn't have data for future dates
3. **Check Logs**: Look for "Incapsula/Imperva challenge detected" messages
4. **Run Debug Tools**: Use `debug_smartpick_url.py` for detailed analysis

#### Frontend CSS Issues
1. **Hard Refresh**: Use Ctrl+Shift+R (Cmd+Shift+R on Mac)
2. **Clear Cache**: Browser cache may need clearing
3. **Check Version**: Ensure CSS files have `?v=2.0.1` query parameters

#### Deployment Issues
1. **Playwright Installation**: May fail on some platforms - fallback scraper available
2. **Memory Limits**: Reduce concurrent scraping if memory issues occur
3. **Timeout Issues**: Increase `SCRAPER_TIMEOUT` environment variable

### **Debugging Resources**
- **SmartPick Debugging Guide**: See `DEBUGGING_SMARTPICK.md`
- **Deployment Guide**: See `DEPLOYMENT_GUIDE.md`
- **2Captcha Setup**: See `docs/2CAPTCHA_SETUP.md`

## 📞 Support

- 📧 **Email**: support@delmar-analyzer.com
- 🐛 **Issues**: [GitHub Issues](https://github.com/your-username/del-mar-analyzer/issues)
- 📖 **Documentation**: [Wiki](https://github.com/your-username/del-mar-analyzer/wiki)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/your-username/del-mar-analyzer/discussions)

---

## 🎯 **Recent Fixes & Improvements**

### **✅ SmartPick Scraper Fix (October 2025)**
- **Root Cause**: Equibase SmartPick pages use Angular/JavaScript for dynamic rendering
- **Solution**: Implemented multiple JavaScript extraction methods
- **Features**:
  - Angular app detection and waiting
  - 5 different data extraction methods
  - Enhanced Incapsula/Imperva challenge handling
  - Improved error handling and logging

### **✅ Frontend CSS Fix (October 2025)**
- **Issue**: Dark theme not loading, JavaScript errors
- **Solution**: Added cache-busting query parameters
- **Result**: Proper styling and theme functionality

### **✅ Enhanced Debugging Tools**
- **debug_smartpick_url.py**: Comprehensive URL and content testing
- **test_smartpick_urls_simple.py**: Quick URL validation
- **smartpick_fix.py**: Complete fix implementation
- **smartpick_scraper_patch.py**: Easy patch application

---

**🔥 Production-ready horse racing analysis platform combining advanced algorithms, AI assistance, and professional presentation. Turn data into profits with confidence-based predictions and strategic betting recommendations.**

---

<sub>*Built with ❤️ by horse racing enthusiasts for horse racing analytics*</sub>