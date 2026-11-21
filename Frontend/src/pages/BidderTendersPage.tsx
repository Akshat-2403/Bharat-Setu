import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, FileText, RefreshCw, Search } from 'lucide-react';
import { fetchTenders } from '@/services/api';
import { formatINR } from '@/utils/formatINR';
import { useTranslation } from '@/i18n';

export default function BidderTendersPage({ searchTerm = '', onOpenBid }: { searchTerm?: string, onOpenBid: (tender: any) => void }) {
  const [tenders, setTenders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const { t } = useTranslation();

  const loadTenders = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    fetchTenders()
      .then(setTenders)
      .catch((error) => {
        console.error('Failed to load tenders:', error);
        setLoadError(true);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadTenders(); }, [loadTenders]);

  const filteredTenders = useMemo(() => tenders.filter((tender) => {
    if (!searchTerm) return true;
    const query = searchTerm.toLowerCase();
    return [tender.tender_id, tender.title, tender.category]
      .some((value) => String(value || '').toLowerCase().includes(query));
  }), [searchTerm, tenders]);

  return (
    <div className="bs-page">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="bs-page-title">{t('tenderFinder')}</h1>
          <p className="bs-page-description">{t('findApplyTenders')}</p>
        </div>
        {!loading && !loadError && tenders.length > 0 && (
          <span className="text-sm text-slate-500" aria-live="polite">{filteredTenders.length} tenders available</span>
        )}
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2" role="status" aria-label="Loading tenders">
          {[0, 1, 2, 3].map((item) => <div key={item} className="bs-card h-64 animate-pulse p-5"><div className="h-5 w-28 rounded bg-slate-100" /><div className="mt-4 h-6 w-3/4 rounded bg-slate-100" /><div className="mt-8 h-20 rounded bg-slate-100" /><span className="sr-only">Loading tenders…</span></div>)}
        </div>
      ) : loadError ? (
        <section className="bs-card px-6 py-12 text-center" role="alert">
          <AlertCircle className="mx-auto mb-3 h-8 w-8 text-amber-700" />
          <h2 className="text-lg font-semibold text-slate-900">Tenders could not be loaded</h2>
          <p className="mt-1 text-sm text-slate-600">Check your connection and try again.</p>
          <button type="button" onClick={loadTenders} className="bs-button-secondary mt-5"><RefreshCw className="h-4 w-4" /> {t('retry')}</button>
        </section>
      ) : filteredTenders.length === 0 ? (
        <section className="bs-card px-6 py-12 text-center" aria-live="polite">
          <Search className="mx-auto mb-3 h-8 w-8 text-slate-400" />
          <h2 className="text-lg font-semibold text-slate-900">{tenders.length ? 'No matching tenders' : 'No active tenders right now'}</h2>
          <p className="mt-1 text-sm text-slate-600">{tenders.length ? 'Try another tender name, reference, or category.' : 'New opportunities will appear here when they are published.'}</p>
        </section>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {filteredTenders.map((tender) => {
            const requirementChips = (tender.requirements || []).filter((req: any) => req.is_mandatory).slice(0, 8);
            const estimatedValue = Number(tender.estimated_value ?? 0);
            return (
              <article key={tender.id} className="bs-card flex min-w-0 flex-col p-5">
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <span className="inline-flex max-w-full truncate rounded-md bg-slate-100 px-2 py-1 font-mono text-[11px] font-semibold text-slate-700">{tender.tender_id}</span>
                    <h2 className="mt-2 text-base font-semibold leading-snug text-slate-900">{tender.title}</h2>
                  </div>
                  <span className="shrink-0 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-800">{t('active')}</span>
                </div>
                <dl className="mb-4 grid grid-cols-1 gap-x-4 gap-y-3 rounded-xl bg-slate-50 p-4 text-sm sm:grid-cols-2">
                  <div><dt className="text-xs text-slate-500">{t('category')}</dt><dd className="mt-0.5 font-medium text-slate-800">{tender.category}</dd></div>
                  <div><dt className="text-xs text-slate-500">{t('deadline')}</dt><dd className="mt-0.5 font-medium text-slate-800">{tender.bid_deadline}</dd></div>
                  <div><dt className="text-xs text-slate-500">{t('estimatedValue')}</dt><dd className="mt-0.5 font-medium text-slate-800">{formatINR(estimatedValue)}</dd></div>
                  <div><dt className="text-xs text-slate-500">{t('minimumExperience')}</dt><dd className="mt-0.5 font-medium text-slate-800">{tender.minimum_experience_years} {t('years')}</dd></div>
                </dl>
                <div className="mb-5 flex-1">
                  <p className="mb-2 text-xs font-semibold text-slate-700">{t('requiredDocuments')}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {requirementChips.length ? requirementChips.map((req: any) => <span key={req.id || req.document_type} className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700">{req.document_type}</span>) : <span className="text-sm text-slate-500">{t('noMandatoryRequirements')}</span>}
                  </div>
                </div>
                <button type="button" onClick={() => onOpenBid(tender)} className="bs-button-primary w-full justify-center"><FileText className="h-4 w-4" /> {t('applyForTender')}</button>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
