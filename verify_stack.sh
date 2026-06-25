#!/bin/bash
echo "=== AUDIT & VERIFICATION REPORT ==="

echo -e "\n1. Checking PostgreSQL..."
export PATH="/home/rai/.postgres_local/usr/lib/postgresql/18/bin:$PATH"
export LD_LIBRARY_PATH="/home/rai/.postgres_local/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH"

if pg_isready -h /tmp -p 5433 >/dev/null 2>&1; then
  echo "✔ PostgreSQL is running and ready on port 5433."
  psql -h /tmp -p 5433 -U rai -d postgres -c "SELECT version();" | head -n 3
else
  echo "✘ PostgreSQL is NOT running or NOT ready on port 5433."
fi

echo -e "\n2. Checking Redis..."
if redis-cli ping | grep -q PONG; then
  echo "✔ Redis is running and responding to PING."
  redis-cli --version
else
  echo "✘ Redis is NOT running or NOT responding."
fi

echo -e "\n3. Checking Qdrant..."
QDRANT_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:6333/readyz)
if [ "$QDRANT_STATUS" = "200" ]; then
  echo "✔ Qdrant is running and ready on port 6333."
  curl -s http://127.0.0.1:6333/readyz
  echo ""
else
  echo "✘ Qdrant is NOT running or NOT responding on port 6333."
fi

echo -e "\n4. Verifying Next.js & Frontend Template Compile..."
cd /home/rai/premium_web_template
if npm run build; then
  echo "✔ Next.js project compiled successfully! (Production-ready check passed)"
else
  echo "✘ Next.js project compile FAILED."
  exit 1
fi

echo -e "\n=== ALL CHECKS COMPLETED ==="
