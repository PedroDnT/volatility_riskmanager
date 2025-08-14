# Deployment Guide: Render Platform

This guide explains how to deploy your Crypto Risk Management System as a web application on Render.

## 🚀 Quick Deploy to Render

### Option 1: One-Click Deploy (Recommended)

1. **Fork this repository** to your GitHub account
2. **Connect to Render**:
   - Go to [Render Dashboard](https://render.com/dashboard)
   - Click "New +" → "Web Service"
   - Connect your GitHub account and select this repository

3. **Configure the deployment**:
   - **Name**: `crypto-risk-manager`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app.py`
   - **Plan**: Start with "Starter" plan (free tier available)

4. **Set Environment Variables**:
   - `BYBIT_API_KEY`: Your Bybit API key
   - `BYBIT_API_SECRET`: Your Bybit API secret
   - `ENVIRONMENT`: `production`
   - `PORT`: `8000` (auto-configured)

5. **Deploy**: Click "Create Web Service"

### Option 2: Manual Deploy via render.yaml

1. **Ensure render.yaml is configured** (already included in repo)
2. **Push to GitHub** and connect repository to Render
3. **Render will auto-detect** the `render.yaml` and deploy automatically

## 🔧 Configuration

### Environment Variables

Set these in your Render dashboard under "Environment":

| Variable | Description | Required |
|----------|-------------|----------|
| `BYBIT_API_KEY` | Your Bybit API key | Yes |
| `BYBIT_API_SECRET` | Your Bybit API secret | Yes |
| `ENVIRONMENT` | Set to `production` | No |
| `PORT` | Port (auto-configured as 8000) | No |

### API Credentials Setup

1. **Create Bybit API Keys**:
   - Go to [Bybit API Management](https://testnet.bybit.com/app/user/api-management) (testnet) or [mainnet](https://www.bybit.com/app/user/api-management)
   - Create new API key with permissions:
     - "Read" permissions (for position data)
     - NO trading permissions needed for risk management
   - Copy the API Key and Secret

2. **Add to Render**:
   - In Render dashboard → Your service → Environment
   - Add `BYBIT_API_KEY` and `BYBIT_API_SECRET`
   - Values are encrypted and secure

## 📊 Features Available in Web Interface

### Dashboard Overview
- **Real-time position monitoring**
- **Portfolio risk metrics**
- **Volatility analysis charts**
- **Stop-loss/Take-profit recommendations**

### Interactive Features
- **Live/Sandbox mode toggle**
- **Auto-refresh every 5 minutes**
- **Manual refresh capability**
- **Detailed position modals**
- **Export analysis to JSON**
- **Responsive mobile design**

### API Endpoints
- `GET /` - Main dashboard
- `GET /api/health` - Health check
- `POST /api/analyze` - Run position analysis
- `GET /api/analysis/latest` - Get latest results
- `POST /api/export` - Export analysis

## 🛠 Development & Testing

### Local Development
```bash
# Clone and setup
git clone <your-repo>
cd market_analysis

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your API credentials

# Run development server
python app.py
# Access at http://localhost:8000
```

### Testing
```bash
# Run tests
pytest -v

# Test web endpoints
curl http://localhost:8000/api/health
```

## 🔒 Security Considerations

### API Key Security
- **Environment Variables**: Credentials stored securely in Render
- **Read-Only Access**: Use read-only API keys when possible
- **No Trading**: Risk management doesn't require trading permissions

### Web Security
- **HTTPS**: All Render deployments use HTTPS by default
- **Input Validation**: All API inputs validated
- **Error Handling**: Sensitive errors not exposed to frontend

## 📈 Performance & Scaling

### Resource Usage
- **Memory**: ~200-400MB typical usage
- **CPU**: Low usage except during analysis runs
- **Storage**: Minimal (only config files)
- **Network**: API calls to Bybit for data

### Caching
- **Analysis Caching**: 5-minute cache for repeated requests
- **Position Data**: Fresh data on each analysis
- **Static Files**: CDN cached (Tailwind, Chart.js)

### Scaling Options
- **Starter Plan**: Free tier, good for personal use
- **Hobby Plan**: $7/month, better performance
- **Professional**: For high-frequency usage

## 🚨 Monitoring & Troubleshooting

### Health Checks
- **Endpoint**: `/api/health`
- **Auto-monitoring**: Render checks every 30 seconds
- **Alerts**: Email notifications on failures

### Common Issues

1. **"No positions found"**
   - Check API credentials
   - Verify you have open positions
   - Try sandbox mode for testing

2. **"Analysis failed"**
   - Check API key permissions
   - Verify network connectivity
   - Review logs in Render dashboard

3. **"Connection Failed"**
   - Check Bybit API status
   - Verify credentials format
   - Try refreshing the page

### Logs
- **Access logs**: Render dashboard → Logs tab
- **Error tracking**: Automatic error capture
- **Debug mode**: Set `ENVIRONMENT=development` for verbose logs

## 🔄 Updates & Maintenance

### Auto-Deploy
- **Git Integration**: Push to main branch auto-deploys
- **Build Process**: ~2-3 minutes for full deploy
- **Zero Downtime**: Rolling deployments

### Manual Updates
```bash
# Update dependencies
pip install -r requirements.txt --upgrade

# Test locally
python app.py

# Commit and push
git add .
git commit -m "Update dependencies"
git push origin main
```

### Backup
- **Configuration**: Store settings.toml in repo
- **Analysis History**: Export JSONs regularly
- **Environment Variables**: Document in secure location

## 💰 Cost Estimation

### Render Pricing (as of 2024)
- **Free Tier**: 750 hours/month (sufficient for personal use)
- **Starter**: $7/month (always-on service)
- **Professional**: $25/month (high performance)

### API Costs
- **Bybit API**: Free for market data
- **Rate Limits**: Well within limits for risk management

## 🌐 Custom Domain (Optional)

1. **Upgrade Plan**: Requires Starter plan or higher
2. **Add Domain**: Render dashboard → Custom Domains
3. **DNS Setup**: Point CNAME to your-service.onrender.com
4. **SSL Certificate**: Auto-provisioned by Render

## 📞 Support

### Resources
- **Render Docs**: [render.com/docs](https://render.com/docs)
- **GitHub Issues**: Use repository issues for bugs
- **API Documentation**: Included in `/docs` endpoint when deployed

### Getting Help
1. Check logs in Render dashboard
2. Review this deployment guide
3. Test locally first
4. Check Bybit API documentation
5. Open GitHub issue with error details

---

## ✅ Deployment Checklist

- [ ] Repository forked/cloned
- [ ] Bybit API credentials ready
- [ ] Render account created
- [ ] Environment variables configured
- [ ] Service deployed successfully
- [ ] Health check passing
- [ ] Dashboard accessible
- [ ] API endpoints working
- [ ] Sandbox mode tested
- [ ] Live mode verified
- [ ] Analysis running correctly
- [ ] Custom domain set up (optional)

🎉 **Your Crypto Risk Management Dashboard is now live!**

Access your deployment at: `https://your-service-name.onrender.com`
