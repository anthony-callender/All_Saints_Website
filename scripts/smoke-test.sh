#!/usr/bin/env bash
# Smoke test for macOS/Linux (bash). Windows: use scripts/smoke-test.ps1.
set -uo pipefail
SITE="http://allsaints.ddev.site"; failed=0
check() { if eval "$2" >/dev/null 2>&1; then echo "  [ok]   $1"; else echo "  [FAIL] $1"; failed=$((failed+1)); fi; }
check "DDEV project running"        "ddev describe | grep -q running"
check "WordPress reachable"         "curl -fsS $SITE/ -o /dev/null"
check "WP-CLI works"                "ddev wp core version"
check "plugin active"               "ddev wp plugin is-active asc-digital-ministry"
check "Sermon CPT exists"           "ddev wp post-type get sermon --field=name"
check "Church Knowledge CPT exists" "ddev wp post-type get church_kb --field=name"
check "chat REST route exists"      "curl -fsS $SITE/wp-json/ | grep -q '/asc/v1/chat'"
check "sermon REST support exists"  "curl -fsS $SITE/wp-json/ | grep -q '/asc/v1/sermons/exists'"
check "Python worker imports"       "(cd worker/sermon_flywheel && python -c 'import sermon_worker.cli')"
check "Python tests pass"           "(cd worker/sermon_flywheel && python -m pytest -q)"
check "WordPress tests pass"        "ddev wp eval-file wp-content/plugins/asc-digital-ministry/tests/run-tests.php"
[ "$failed" -eq 0 ] && echo "All smoke checks passed" || { echo "$failed check(s) failed"; exit 1; }
