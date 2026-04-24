# Deployment — Amazon Linux 2023 + nginx + systemd + GitHub Actions

```
GitHub push ──▶ Actions ──ssh──▶ EC2 ──▶ git pull + pip + systemctl restart
EC2: nginx (443/SSL) ──proxy──▶ Flask (127.0.0.1:8000, systemd)
```

---

## A. Initial server setup (run ONCE on EC2)

SSH to EC2, then:

```bash
# 1. Get the new code (overwrite the old version)
cd /home/ec2-user/vya
git fetch --all
git reset --hard origin/main

# 2. Run the setup script (installs nginx, certbot, systemd, etc.)
bash deploy/setup.sh
```

The script will tell you to edit `.env` with your real keys. Do that, then:

```bash
nano /home/ec2-user/vya/.env       # paste your real keys
sudo systemctl restart vya-kitchen
```

### Get HTTPS (one-time)

```bash
sudo certbot --nginx -d vya.co.nz -d www.vya.co.nz \
  --non-interactive --agree-tos -m ebin198351@gmail.com --redirect
```

certbot auto-renews via cron. To verify:

```bash
sudo systemctl status certbot-renew.timer
```

Open `https://vya.co.nz` — should show the site.

---

## B. GitHub Actions auto-deploy (run ONCE locally + GH UI)

### 1. Generate a deploy SSH key (on your Mac)

```bash
ssh-keygen -t ed25519 -f ~/.ssh/vya_deploy_key -N "" -C "github-actions-deploy"
```

This makes 2 files:
- `~/.ssh/vya_deploy_key`         (private — NEVER commit)
- `~/.ssh/vya_deploy_key.pub`     (public)

### 2. Add public key to EC2

Copy the public key into EC2's authorized_keys:

```bash
cat ~/.ssh/vya_deploy_key.pub | ssh -i ~/.ssh/your-existing-aws.pem ec2-user@3.25.163.163 \
  'cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
```

### 3. Add 3 secrets in GitHub UI

Go to: `https://github.com/ebin198351-akl/vya_bun/settings/secrets/actions`

Click **New repository secret** for each:

| Name       | Value                                       |
|------------|---------------------------------------------|
| `SSH_HOST` | `3.25.163.163`                              |
| `SSH_USER` | `ec2-user`                                  |
| `SSH_KEY`  | (paste contents of `~/.ssh/vya_deploy_key`, including `-----BEGIN…END-----` lines) |

### 4. Test it

Make any tiny change locally, commit & push:

```bash
git commit --allow-empty -m "test: trigger deploy"
git push
```

Then watch: `https://github.com/ebin198351-akl/vya_bun/actions`

If green ✓ → you're done. Future pushes deploy automatically.

---

## C. Manual override commands (cheat sheet)

On EC2:

```bash
# View running status
sudo systemctl status vya-kitchen

# Restart manually
sudo systemctl restart vya-kitchen

# Tail logs (live)
sudo journalctl -u vya-kitchen -f
# or
tail -f /home/ec2-user/vya/server.log

# Force a manual deploy (without GH Actions)
cd /home/ec2-user/vya
git fetch && git reset --hard origin/main
python3 -m pip install --user -r requirements.txt
sudo systemctl restart vya-kitchen

# Inspect nginx
sudo nginx -t                  # config syntax
sudo systemctl reload nginx    # reload config
sudo tail -f /var/log/nginx/error.log

# Renew SSL (auto, but to test):
sudo certbot renew --dry-run
```

---

## D. Troubleshooting

| Symptom | Fix |
|---|---|
| `502 Bad Gateway` from nginx | Flask isn't running. `sudo systemctl status vya-kitchen` and check `journalctl -u vya-kitchen -n 50` |
| Site returns "Internal Server Error" | Likely missing env var. Check `/home/ec2-user/vya/.env` and restart |
| GH Actions stuck on "Connecting" | EC2 security group blocks port 22 from GitHub IPs. Open 22 to `0.0.0.0/0` (SSH key auth is the gate) |
| GH Actions error "permission denied" | SSH_KEY secret is wrong or has wrong permissions. Re-paste full private key including header/footer |
| Certbot fails | DNS not yet propagated. Run `dig vya.co.nz` to verify A record points to your EC2 IP |
| `vya-kitchen` won't start | `sudo journalctl -u vya-kitchen -n 50` — usually a Python ImportError or .env missing |

---

## E. Roll back

If a deploy breaks production:

```bash
cd /home/ec2-user/vya
git log --oneline -5             # find the good commit
git reset --hard <good-sha>
sudo systemctl restart vya-kitchen
```

This decouples you from GitHub state — manual override always wins.
