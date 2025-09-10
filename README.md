# 🏇 Del Mar Race Analysis Application

[![Deploy to Render](https://img.shields.io/badge/Deploy-Render-4A90E2)](https://render.com)
![Python Version](https://img.shields.io/badge/python-3.11-blue.svg)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**AI-Powered Horse Racing Scraper, Analyzer & Prediction Platform**

Transform racing data into profitable insights with advanced machine learning algorithms, sophisticated web scraping, and professional betting recommendations.

## 🚀 Features

### 🤖 **AI-Powered Analysis**
- **Multiple LLM Integration**: GPT-4o, Claude-3, and more via OpenRouter
- **Intelligent Scraping**: AI-guided page analysis and CAPTCHA navigation
- **Smart Predictions**: Advanced confidence scoring and risk assessment
- **Professional Recommendations**: Complete betting strategy analysis

### 📊 **Advanced Analytics**
- **6-Factor Prediction Engine**: Speed (25%), Class (15%), Form (20%), Workout (15%), Jockey (8%), Trainer (7%)
- **Track-Specific Heuristics**: Del Mar optimized with rail position analysis
- **Real-time Data**: Live horse stats, odds, and performance metrics
- **Comprehensive Reports**: Professional-formatted analysis with betting recommendations

### 🦿 **Sophisticated Scraping**
- **Performance**: Top-tier scraping with anti-detection measures
- **Reliability**: Multi-layered fallback strategies for maximum uptime
- **Compliance**: Respectful rate limiting and user-agent rotation
- **Scale**: Handle complete race cards with parallel processing

## 🏗️ Architecture

```
Del Mar Analyzer/
├── FastAPI Web Framework
├── SQLite Database (Production Ready)
├── Playwright Browser Automation
├── OpenRouter AI Integration
├── Advanced Prediction Engine
└── Professional Web Interface
```

### 📁 **Project Structure**
```bash
del-mar-race-analyzer/
├── app.py                              # Main FastAPI application
├── race_prediction_engine.py          # Advanced prediction algorithms
├── scrapers/                          # Web scraping infrastructure
│   ├── playwright_equibase_scraper.py
│   └── smartpick_scraper.py
├── services/                          # Business logic layer
│   ├── orchestration_service.py
│   ├── openrouter_client.py
│   └── session_manager.py
├── core/                              # Data models and utilities
│   └── horse_data.py
├── templates/                         # Jinja2 web templates
│   ├── landing.html
│   ├── progress.html
│   ├── results.html
│   └── error.html
├── static/                            # CSS, JS, images
├── config/                            # Configuration management
├── render-deploy/                     # Production deployment
│   ├── render.yaml
│   └── Dockerfile
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

# Optional
ENVIRONMENT=production          # development/production
LOG_LEVEL=INFO                  # DEBUG/INFO/WARNING/ERROR
DATABASE_URL=sqlite:///./del_mar_analyzer.db
SCRAPER_HEADLESS=true           # false for debugging
SCRAPER_TIMEOUT=30              # scraping timeout in seconds
SECRET_KEY=your_secret_key      # for secure sessions
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

## 🧪 Testing

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run the test suite
pytest tests/ -v

# Run coverage report
pytest --cov=del_mar_analyzer tests/
```

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

## 📞 Support

- 📧 **Email**: support@delmar-analyzer.com
- 🐛 **Issues**: [GitHub Issues](https://github.com/your-username/del-mar-analyzer/issues)
- 📖 **Documentation**: [Wiki](https://github.com/your-username/del-mar-analyzer/wiki)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/your-username/del-mar-analyzer/discussions)

---

**🔥 Production-ready horse racing analysis platform combining advanced algorithms, AI assistance, and professional presentation. Turn data into profits with confidence-based predictions and strategic betting recommendations.**

---

<sub>*Built with ❤️ by horse racing enthusiasts for horse racing analytics*</sub>