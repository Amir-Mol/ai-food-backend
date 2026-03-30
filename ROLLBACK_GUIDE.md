# Database Migration Rollback Guide

## Overview
This guide provides procedures for rolling back the Version2 database migrations if needed.

## Phase 1 Rollback: Version2 Fields

### Quick Rollback (Local Development)

If you haven't pushed to remote yet:

```bash
# Revert the migration
cd backend
prisma migrate resolve --rolled-back 20260330000000_add_version2_fields

# Delete the migration directory
rm -rf prisma/migrations/20260330000000_add_version2_fields/

# Reset your local database
prisma migrate reset  # This will prompt you - confirm to reset
```

### Production Rollback (CSC Rahti)

If deployed to CSC Pukki (production database), follow this procedure:

#### Step 1: Create Rollback Migration

```bash
cd backend

# Create a new down migration that removes the fields
cat > prisma/migrations/20260330000001_rollback_version2_fields/migration.sql << 'EOF'
-- Rollback: Remove Version2 fields from User table
ALTER TABLE "User" DROP COLUMN IF EXISTS "feedbackSummaryForEmbedding";
ALTER TABLE "User" DROP COLUMN IF EXISTS "feedbackSummaryForLLM";
ALTER TABLE "User" DROP COLUMN IF EXISTS "feedbackSummaryLastUpdatedAt";
ALTER TABLE "User" DROP COLUMN IF EXISTS "recommendationGenerationStatus";
ALTER TABLE "User" DROP COLUMN IF EXISTS "recommendationsReadyAt";
ALTER TABLE "User" DROP COLUMN IF EXISTS "nextAllowedGenerationAt";
ALTER TABLE "User" DROP COLUMN IF EXISTS "recommendations";
EOF
```

#### Step 2: Apply Rollback Migration

```bash
# Using OpenShift port-forward to CSC Pukki database
oc port-forward pods/postgresql-pod 5432:5432 &

# Apply the rollback
psql -U postgres -h localhost -d recipe_db -f prisma/migrations/20260330000001_rollback_version2_fields/migration.sql

# Verify columns are removed
psql -U postgres -h localhost -d recipe_db -c "\d \"User\""

# Kill port-forward
jobs -l  # find the port-forward job
kill %1  # or use the job number
```

#### Step 3: Update Prisma Schema

```bash
# Edit prisma/schema.prisma and remove the 7 Version2 fields from User model
# Then run:
prisma generate  # Regenerate Prisma client
```

#### Step 4: Deploy to Rahti

```bash
git add prisma/
git commit -m "Rollback: Remove Version2 fields from User model"
git push origin csc-migration

# Push to OpenShift deployment
oc set image deployment/backend-app \
  backend-app=<image-registry>/backend:$(git rev-parse --short HEAD) \
  --record

# Verify deployment
oc logs -f deployment/backend-app
```

## Phase 2-4 Code Rollback

Since Phase 2-4 implemented new code (not database changes), rollback is simpler:

```bash
# Revert specific commits
git revert HEAD~3..HEAD  # Adjust the number of commits as needed

# Or revert to a specific commit
git reset --hard cafb7a4  # Replace with commit hash before Phase 2

# Push to remote
git push origin csc-migration --force-with-lease
```

## Data Recovery

If you accidentally deleted user data during a rollback:

### CSC Pukki Backup Recovery

```bash
# List available backups
oc get backups

# Restore from backup
oc restore <backup-name> --to-time="<timestamp>"

# Verify restoration
psql -U postgres -h <restored-db-host> -d recipe_db -c "SELECT COUNT(*) FROM \"User\";"
```

## Testing Rollback

Before rolling back production:

1. **Test on staging database** - Always test first
2. **Create backup** - Backup production before rollback
3. **Brief downtime** - Schedule rollback during low-traffic hours
4. **Validation checks** - Verify existing endpoints still work

### Post-Rollback Validation

```bash
# Check API endpoints still work
curl -H "Authorization: Bearer <token>" \
  https://your-api.example.com/api/recommendations

# Verify no orphaned tables
psql -U postgres -h <db-host> -d recipe_db -c "\dt"

# Check logs for errors
oc logs -f deployment/backend-app --tail=100
```

## Prevention Tips

1. **Always test migrations locally first**
2. **Maintain backups before major changes**
3. **Use feature branches for experimental work**
4. **Keep migrations simple and isolated**
5. **Document rollback procedures before deploying**

## Contact Support

If rollback fails or you need assistance:

1. Check CSC Rahti logs: `oc logs -f deployment/backend-app`
2. Review migration files: `ls -la prisma/migrations/`
3. Confirm database connection: `psql -U postgres -h <db-host> -d recipe_db -c "SELECT 1;"`

---

**Last Updated**: March 30, 2026  
**Scope**: Version2 Implementation Phases 1-4  
**Test Status**: Designed for CSC Pukki + Rahti OpenShift
