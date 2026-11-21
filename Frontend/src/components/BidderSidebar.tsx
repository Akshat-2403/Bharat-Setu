import {
  ShieldCheck,
  LayoutDashboard,
  FileSearch,
  ClipboardCheck,
  Building2,
  AlertTriangle,
  History,
  Settings,
  HelpCircle,
  LogOut,
  PlusCircle,
  FileText,
  Bell
} from 'lucide-react';
import { useTranslation } from '@/i18n';

interface SidebarProps {
  currentTab: string;
  onTabChange: (tab: string) => void;
  onOpenNewBid: () => void;
  currentUser: any;
}

const navItems = [
  { id: 'dashboard', icon: LayoutDashboard, key: 'dashboard' },
  { id: 'tenders', icon: FileSearch, key: 'tenderFinder' },
  { id: 'bids', icon: ClipboardCheck, key: 'myBids' },
  { id: 'documents', icon: FileText, key: 'myDocuments' },
  { id: 'alerts', icon: AlertTriangle, key: 'complianceAlerts' },
];

const bottomItems = [
  { id: 'support', icon: HelpCircle, key: 'aiSupport' },
  { id: 'settings', icon: Settings, key: 'settings' },
];

export default function BidderSidebar({ currentTab, onTabChange, onOpenNewBid, currentUser }: SidebarProps) {
  const { t } = useTranslation();
  const translatedLabels: Record<string, string> = {
    dashboard: t('dashboard'),
    support: t('help'),
    tenders: t('tenderFinder'),
    bids: t('myBids'),
    documents: t('myDocuments'),
    alerts: t('complianceAlerts'),
    settings: t('settings'),
    logout: t('logout'),
  };
  return (
    <aside className="sticky top-0 z-30 flex h-screen w-16 shrink-0 flex-col bg-slate-900 text-white md:w-64">
      {/* Logo */}
      <div className="border-b border-white/10 px-2 py-4 md:px-5 md:py-5">
        <div className="flex items-center justify-center gap-3 md:justify-start">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-indigo-500 to-indigo-700 flex items-center justify-center shadow-lg">
            <Building2 className="w-6 h-6 text-white" strokeWidth={2.2} />
          </div>
          <div className="hidden md:block">
            <h1 className="font-bold text-[15px] leading-tight tracking-tight">BharatSetu</h1>
            <p className="text-[11px] text-indigo-300 font-medium">{t('bidderPortal')}</p>
          </div>
        </div>
      </div>

      {/* New Bid Action */}
      <div className="px-2 pt-3 pb-2 md:px-3 md:pt-4">
        <button
          onClick={onOpenNewBid}
          title={t('startBidUploadDocuments')}
          aria-label={t('startBidUploadDocuments')}
          className="flex min-h-11 w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-2 py-2.5 text-xs font-bold text-white shadow-md transition-all hover:bg-indigo-700 md:px-3"
        >
          <PlusCircle className="w-4 h-4" />
          <span className="hidden md:inline">{t('startBidUploadDocuments')}</span>
        </button>
        <p className="hidden px-1 pt-2 text-[10px] leading-relaxed text-slate-400 md:block">{t('chooseTenderForDocuments')}</p>
      </div>

      {/* Nav */}
      <nav className="scrollbar-navy flex-1 overflow-y-auto px-2 py-2 md:px-3">
        <p className="mb-2 hidden px-3 text-[10px] font-semibold uppercase tracking-wider text-slate-400 md:block">
          {t('vendorModules')}
        </p>
        <ul className="space-y-1">
          {navItems.map((item) => {
            const isActive = currentTab === item.id;
            return (
              <li key={item.id}>
                <button
                  onClick={() => onTabChange(item.id)}
                  title={translatedLabels[item.id] || item.key}
                  aria-label={translatedLabels[item.id] || item.key}
                  aria-current={isActive ? 'page' : undefined}
                  className={`group flex w-full items-center justify-center gap-3 rounded-lg px-2 py-3 text-sm font-medium transition-all duration-150 md:justify-start md:px-3 md:py-2.5 ${
                    isActive
                      ? 'bg-slate-800 text-white shadow-md border border-slate-700'
                      : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                  }`}
                >
                  <item.icon className="w-[18px] h-[18px] shrink-0" strokeWidth={2} />
                  <span className="hidden flex-1 text-left md:inline">{translatedLabels[item.id] || item.key}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Bottom */}
      <div className="border-t border-white/10 px-2 py-3 md:px-3">
        <ul className="space-y-1">
          {bottomItems.map((item) => (
            <li key={item.id}>
              <button
                onClick={() => onTabChange(item.id)}
                title={translatedLabels[item.id] || item.key}
                aria-label={translatedLabels[item.id] || item.key}
                className="flex w-full items-center justify-center gap-3 rounded-lg px-2 py-3 text-sm font-medium text-slate-300 transition-all duration-150 hover:bg-slate-800 hover:text-white md:justify-start md:px-3 md:py-2"
              >
                <item.icon className="w-[18px] h-[18px] shrink-0" strokeWidth={2} />
                <span className="hidden md:inline">{translatedLabels[item.id] || item.key}</span>
              </button>
            </li>
          ))}
          <li>
            <button
                onClick={() => onTabChange('logout')}
              title={t('logout')}
              aria-label={t('logout')}
              className="flex w-full items-center justify-center gap-3 rounded-lg px-2 py-3 text-sm font-medium text-slate-300 transition-all duration-150 hover:bg-red-500/20 hover:text-red-400 md:justify-start md:px-3 md:py-2"
              >
                <LogOut className="w-[18px] h-[18px] shrink-0" strokeWidth={2} />
                <span className="hidden md:inline">{t('logout')}</span>
            </button>
          </li>
        </ul>
      </div>

      {/* User card */}
      <div className="hidden px-3 pb-4 md:block">
        <div className="flex items-center gap-3 rounded-xl border border-slate-700 bg-slate-800 p-3">
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-indigo-400 to-indigo-600 flex items-center justify-center text-white font-bold text-sm shrink-0">
            {currentUser?.full_name?.charAt(0) || 'U'}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white truncate">{currentUser?.full_name || t('vendor')}</p>
            <p className="text-[11px] text-slate-400 truncate">{currentUser?.department || t('vendor')}</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
