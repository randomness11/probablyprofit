# Security Best Practices

Guidelines for safely running ProbablyProfit in production.

## Secrets Management

### Never Commit Secrets
- **NEVER** commit `.env` files to version control
- The `.gitignore` already excludes `.env`, but double-check
- If you accidentally commit a secret, rotate it immediately

### Use Environment Variables
Instead of passing secrets as command-line arguments:
```bash
# BAD - visible in process list
python main.py --api-key sk-ant-123456

# GOOD - use environment variables
export ANTHROPIC_API_KEY=sk-ant-123456
python main.py
```

### Secure Your .env File
```bash
# Set restrictive permissions
chmod 600 .env

# Verify
ls -la .env
# Should show: -rw------- (only owner can read/write)
```

## API Keys

### Anthropic/OpenAI/Google
- Create separate API keys for different environments (dev/staging/prod)
- Set usage limits in the provider dashboard
- Monitor usage for unexpected spikes
- Rotate keys periodically (every 90 days recommended)

### Polymarket Private Key
This is your Polygon wallet private key. Handle with extreme care:
- **NEVER** share it with anyone
- Use a dedicated wallet for trading, not your main wallet
- Only fund it with what you're willing to lose
- Consider using a hardware wallet for large amounts

## Production Deployment

### Use a Secrets Manager
For production deployments, consider:
- AWS Secrets Manager
- HashiCorp Vault
- Google Secret Manager
- Azure Key Vault

Example with AWS:
```python
import boto3

def get_secret(name):
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=name)
    return response['SecretString']
```

### Docker Security
If running in Docker:
```yaml
# docker-compose.yml
services:
  bot:
    # Don't use root
    user: "1000:1000"
    # Read-only filesystem where possible
    read_only: true
    # Drop unnecessary capabilities
    cap_drop:
      - ALL
    # Set resource limits
    deploy:
      resources:
        limits:
          memory: 512M
```

### Network Security
- Run behind a reverse proxy (nginx, Caddy)
- Use HTTPS for all API endpoints
- Restrict API access to trusted IPs
- Use firewall rules to limit outbound connections

## Logging and Monitoring

### Redact Secrets from Logs
ProbablyProfit automatically redacts common secret patterns, but:
- Don't log full request/response bodies that might contain secrets
- Review logs before sharing in bug reports
- Use `logger.debug()` for sensitive data (disabled in production)

### Audit Trail
Keep records of:
- All trades executed
- Configuration changes
- Emergency stop activations
- Authentication events

## Risk Controls

### Use the Kill Switch
The kill switch stops all trading immediately:
```bash
# Activate
touch /tmp/probablyprofit.stop

# Or via API
curl -X POST http://localhost:8000/api/emergency-stop?reason=manual
```

### Set Conservative Limits
Start with conservative risk limits:
```bash
MAX_POSITION_SIZE=50      # Small positions
MAX_TOTAL_EXPOSURE=500    # Limited total exposure
MAX_DAILY_LOSS=100        # Stop after modest loss
MAX_DRAWDOWN_PCT=20       # Auto-stop at 20% drawdown
```

### Paper Trading First
Always test strategies in paper trading mode before going live:
```bash
python -m probablyprofit.main --paper "your strategy"
```

## Incident Response

### If You Suspect Compromise
1. **Immediately** activate the kill switch
2. Rotate ALL API keys
3. Transfer funds to a new wallet
4. Review logs for unauthorized access
5. Check for unauthorized trades

### Emergency Contacts
- Polymarket support: [support@polymarket.com]
- AI provider security: Check their security documentation

## Security Checklist

Before going live:
- [ ] `.env` file is NOT in version control
- [ ] `.env` file has restrictive permissions (600)
- [ ] Using dedicated wallet (not main wallet)
- [ ] API keys have usage limits set
- [ ] Risk limits are configured conservatively
- [ ] Kill switch is tested and working
- [ ] Logs don't contain secrets
- [ ] Running as non-root user
- [ ] Paper trading tested successfully
