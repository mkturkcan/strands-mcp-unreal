# Strands Agent System Management

This directory contains scripts to manage the Strands shared global agent system on this EC2 instance.

## Quick Start

### Start the System
```batch
# Option 1: Batch script
start_strands_system.bat

# Option 2: PowerShell (recommended)
powershell -ExecutionPolicy Bypass -File start_strands_system.ps1
```

### Check Status
```powershell
powershell -ExecutionPolicy Bypass -File check_strands_status.ps1
```

### Stop the System
```powershell
powershell -ExecutionPolicy Bypass -File stop_strands_system.ps1
```

## System Architecture

```
User Browser → CloudFront → api.thedimessquare.com (ALB) → EC2:8002 → MCP:8000 → Unreal Engine
```

## Services Overview

| Service | Port | URL | Purpose |
|---------|------|-----|---------|
| MCP Server | 8000 | http://localhost:8000/mcp | Unreal Engine communication |
| HTTP Agent Server | 8002 | http://localhost:8002/ | Internal ALB backend |
| HTTPS Agent Server | 8443 | https://localhost:8443/ | Direct HTTPS access |
| Public API | 443 | https://api.thedimessquare.com/ | Public endpoint via ALB |

## Frontend URLs

- **CloudFront**: https://d1u690gz6k82jo.cloudfront.net/
- **Production API**: https://api.thedimessquare.com/

## Key Features

✅ **Shared Global Agent**: All users share one agent that processes commands sequentially  
✅ **Command Queue**: Multiple users can submit commands that are processed in order  
✅ **Real-time Updates**: WebSocket broadcasting to all connected clients  
✅ **SSL/TLS**: Trusted certificates via AWS Certificate Manager  
✅ **Load Balancing**: AWS ALB handles SSL termination and routing  
✅ **Auto-scaling**: Ready for multiple EC2 instances if needed  

## Files Created

- `start_strands_system.bat` - Windows batch startup script
- `start_strands_system.ps1` - PowerShell startup script (recommended)
- `stop_strands_system.ps1` - PowerShell stop script
- `check_strands_status.ps1` - System status checker
- `strands_processes.json` - Runtime process tracking (auto-generated)

## AWS Infrastructure

### Route 53
- A record: `api.thedimessquare.com` → ALB
- CNAME validation for SSL certificate

### Certificate Manager
- SSL certificate for `api.thedimessquare.com`
- Auto-renewal enabled

### Application Load Balancer
- **Name**: strands-api-lb
- **HTTPS Listener**: Port 443 → Target Group (EC2:8002)
- **HTTP Listener**: Port 80 → Redirect to HTTPS
- **Health Checks**: HTTP GET / every 30s

### Target Group
- **Name**: strands-api-targets  
- **Protocol**: HTTP
- **Port**: 8002
- **Health Check**: HTTP GET /

## Troubleshooting

### If services won't start:
1. Check if ports are in use: `netstat -ano | findstr ":8000 :8002 :8443"`
2. Kill any stuck processes: `stop_strands_system.ps1`
3. Restart EC2 instance if needed

### If external API not responding:
1. Check ALB status in AWS Console
2. Verify target group health
3. Check DNS propagation: `nslookup api.thedimessquare.com`

### If frontend can't connect:
1. Verify SSL certificate is valid
2. Check CORS settings in shared_agent_server.py
3. Check browser developer tools for errors

## Daily Operation

### Morning Startup (after resuming EC2):
```powershell
cd "C:\Users\Administrator\Documents\Unreal Projects"
powershell -ExecutionPolicy Bypass -File start_strands_system.ps1
```

### Evening Shutdown (before pausing EC2):
```powershell
powershell -ExecutionPolicy Bypass -File stop_strands_system.ps1
```

### Health Check:
```powershell
powershell -ExecutionPolicy Bypass -File check_strands_status.ps1
```

## Integration with TheDimesSquare.com

The system is ready for integration:

1. **Embed Option**: Add iframe to main site
   ```html
   <iframe src="https://d1u690gz6k82jo.cloudfront.net/" width="100%" height="600px"></iframe>
   ```

2. **Full-screen Link**: Direct users to dedicated experience
   ```html
   <a href="https://d1u690gz6k82jo.cloudfront.net/" target="_blank">Launch Strands Agent</a>
   ```

3. **Custom Integration**: Copy frontend code and customize for your site design

---

**System Status**: ✅ Ready for Production  
**Last Updated**: $(Get-Date)  
**EC2 Instance**: i-04bcee1a80b8c7839  
**Region**: us-east-1  