# ⚠️ DEPRECATED

**This dashboard implementation is deprecated.**

## Status

This `app/dashboard/` directory is kept for reference only and will be removed in a future release.

## Migration

Please use the **main frontend** located at `AI_support/frontend/`.

### Shared Types

Dashboard types have been unified and are now available at:
```
AI_support/frontend/src/types/dashboard.ts
```

### Components Migrated

The following components have been migrated to `AI_support/frontend/src/components/ui/`:
- `StatusIndicator`
- `ProgressBar`
- `Table`
- `MetricCard`

### Backend

The Python backend endpoints remain unchanged and serve both frontend implementations:
```
/api/dashboard/overview
/api/dashboard/health
/api/dashboard/workflows
/api/dashboard/timeline
/api/dashboard/hardware
/api/dashboard/tokens
```

## Timeline

- **v1.5**: Marked as deprecated
- **v2.0**: Will be removed

## Questions?

Open an issue at https://github.com/carv-ai/carv/issues
