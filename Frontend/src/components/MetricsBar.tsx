import { useEffect, useState } from 'react';
import { ClipboardList, CheckCircle2, Clock, AlertTriangle, RefreshCw } from 'lucide-react';
import { fetchDashboardMetrics, DashboardMetrics } from '@/services/api';
import { useTranslation } from '@/i18n';

const colorMap: Record<string, { bg: string; text: string; ring: string }> = {
  navy: { bg: 'bg-navy-50', text: 'text-navy-700', ring: 'ring-navy-100' },
  emerald: { bg: 'bg-emerald-50', text: 'text-emerald-600', ring: 'ring-emerald-100' },
  amber: { bg: 'bg-amber-50', text: 'text-amber-600', ring: 'ring-amber-100' },
  red: { bg: 'bg-red-50', text: 'text-red-600', ring: 'ring-red-100' },
};

export default function MetricsBar() {
  const { t } = useTranslation();
  const [data, setData] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const loadMetrics = () => {
    setLoading(true);
    setLoadError(false);
    fetchDashboardMetrics()
      .then(setData)
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadMetrics(); }, []);

  const metrics = data
    ? [
        {
          label: t('pendingReview'),
          value: String(data.pending_review_count),
          sub: t('awaitingOfficerDecision'),
          icon: ClipboardList,
          color: 'navy',
          trend: null,
        },
        {
          label: t('approvedBids'),
          value: String(data.approved_today_count),
          sub: t('complianceVerified'),
          icon: CheckCircle2,
          color: 'emerald',
          trend: null,
        },
        {
          label: t('averageVerificationTime'),
          value: data.avg_verification_time,
          sub: t('endToEndProcessing'),
          icon: Clock,
          color: 'amber',
          trend: null,
        },
        {
          label: t('flaggedCases'),
          value: String(data.flagged_cases_count),
          sub: t('requireEscalation'),
          icon: AlertTriangle,
          color: 'red',
          trend: null,
        },
      ]
    : [];

  if (loading && !data) {
    return (
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4" role="status" aria-label="Loading dashboard metrics">
        {[0, 1, 2, 3].map((item) => <div key={item} className="h-32 animate-pulse rounded-2xl border border-slate-200 bg-white p-5"><div className="h-8 w-24 rounded bg-slate-100" /><div className="mt-6 h-6 w-16 rounded bg-slate-100" /><div className="mt-2 h-3 w-28 rounded bg-slate-100" /></div>)}
        <span className="sr-only">Loading metrics…</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div role="alert" className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <span>{loadError ? t('metricsUnavailable') : 'Dashboard metrics are not available.'}</span>
        <button type="button" onClick={loadMetrics} className="inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-white px-3 py-2 text-xs font-semibold text-amber-900 hover:bg-amber-100">
          <RefreshCw className="h-3.5 w-3.5" /> {t('retry')}
        </button>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {metrics.map((m) => {
        const c = colorMap[m.color];
        return (
          <div
            key={m.label}
            className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md"
          >
            <div className="flex items-start justify-between mb-3">
              <div className={`w-11 h-11 rounded-lg ${c.bg} ${c.text} flex items-center justify-center ring-1 ${c.ring}`}>
                <m.icon className="w-[22px] h-[22px]" strokeWidth={2} />
              </div>
            </div>
            <p className="mb-1 text-xs font-medium text-slate-500">{m.label}</p>
            <div className="flex items-baseline gap-2">
              <p className="text-2xl font-semibold tracking-tight text-slate-900">{m.value}</p>
            </div>
            <p className="text-[12px] text-slate-400 mt-1">{m.sub}</p>
          </div>
        );
      })}
    </div>
  );
}
