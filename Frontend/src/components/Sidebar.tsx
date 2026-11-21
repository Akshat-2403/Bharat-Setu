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
  PlusCircle
} from 'lucide-react';
import { useTranslation } from '@/i18n';

interface SidebarProps {
  currentTab: string;
  onTabChange: (tab: string) => void;
  onOpenNewBid: () => void;
  currentUser?: any;
}

const navItems: Array<{ id: string; icon: typeof LayoutDashboard; label: string; badge?: string }> = [
  { id: 'dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { id: 'queue', icon: FileSearch, label: 'Verification Queue' },
  { id: 'tenders', icon: ClipboardCheck, label: 'Tenders' },
  { id: 'reviewed', icon: ClipboardCheck, label: 'Reviewed Bids' },
  { id: 'vendors', icon: Building2, label: 'Vendor Registry' },
  { id: 'flagged', icon: AlertTriangle, label: 'Flagged Cases' },
  { id: 'audit', icon: History, label: 'Audit History' },
];

const bottomItems = [
  { id: 'settings', icon: Settings, label: 'Settings' },
  { id: 'support', icon: HelpCircle, label: 'Help & Support' },
];

export default function Sidebar({ currentTab, onTabChange, onOpenNewBid, currentUser }: SidebarProps) {
  const { t } = useTranslation();
  const labels: Record<string, string> = {
    dashboard: t('dashboard'),
    queue: t('verificationQueue'),
    tenders: t('tenders'),
    reviewed: t('reviewedBids'),
    vendors: t('vendorRegistry'),
    flagged: t('flaggedCases'),
    audit: t('auditHistory'),
    settings: t('settings'),
    support: t('helpSupport'),
  };
  return (
    <aside className="sticky top-0 z-30 flex h-screen w-16 shrink-0 flex-col bg-navy-950 text-white md:w-64">
      {/* Logo */}
      <div className="border-b border-white/10 px-2 py-4 md:px-5 md:py-5">
        <div className="flex items-center justify-center gap-3 md:justify-start">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-navy-400 to-navy-600 flex items-center justify-center shadow-lg">
            <ShieldCheck className="w-6 h-6 text-white" strokeWidth={2.2} />
          </div>
          <div className="hidden md:block">
            <h1 className="font-bold text-[15px] leading-tight tracking-tight">BharatSetu</h1>
            <p className="text-[11px] text-navy-300 font-medium">{t('procurementOperations')}</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-2 overflow-y-auto scrollbar-navy">
        <p className="mb-2 hidden px-3 text-[10px] font-semibold uppercase tracking-wider text-navy-400 md:block">
          {t('procurementModules')}
        </p>
        <ul className="space-y-1">
          {navItems.map((item) => {
            const isActive = currentTab === item.id;
            return (
              <li key={item.id}>
                <button
                  onClick={() => onTabChange(item.id)}
                  title={labels[item.id] || item.label}
                  aria-label={labels[item.id] || item.label}
                  aria-current={isActive ? 'page' : undefined}
                  className={`group flex w-full items-center justify-center gap-3 rounded-lg px-2 py-3 text-sm font-medium transition-all duration-150 md:justify-start md:px-3 md:py-2.5 ${
                    isActive
                      ? 'bg-navy-600 text-white shadow-md'
                      : 'text-navy-200 hover:bg-navy-800 hover:text-white'
                  }`}
                >
                  <item.icon className="w-[18px] h-[18px] shrink-0" strokeWidth={2} />
                  <span className="hidden flex-1 text-left md:inline">{labels[item.id] || item.label}</span>
                  {item.badge && (
                    <span
                      className={`text-[11px] font-bold px-1.5 py-0.5 rounded-md ${
                        isActive ? 'bg-white/20' : 'bg-navy-700 text-navy-200'
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
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
                title={labels[item.id] || item.label}
                aria-label={labels[item.id] || item.label}
                className="flex w-full items-center justify-center gap-3 rounded-lg px-2 py-3 text-sm font-medium text-navy-200 transition-all duration-150 hover:bg-navy-800 hover:text-white md:justify-start md:px-3 md:py-2"
              >
                <item.icon className="w-[18px] h-[18px] shrink-0" strokeWidth={2} />
                <span className="hidden md:inline">{labels[item.id] || item.label}</span>
              </button>
            </li>
          ))}
          <li>
            <button
              onClick={() => onTabChange('logout')}
              title={t('logout')}
              aria-label={t('logout')}
              className="flex w-full items-center justify-center gap-3 rounded-lg px-2 py-3 text-sm font-medium text-navy-200 transition-all duration-150 hover:bg-red-500/20 hover:text-red-400 md:justify-start md:px-3 md:py-2"
            >
              <LogOut className="w-[18px] h-[18px] shrink-0" strokeWidth={2} />
              <span className="hidden md:inline">{t('logout')}</span>
            </button>
          </li>
        </ul>
      </div>

      {/* Officer card */}
      <div className="hidden px-3 pb-4 md:block">
        <div className="flex items-center gap-3 rounded-xl bg-navy-800 p-3">
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center text-navy-950 font-bold text-sm shrink-0">
            {currentUser?.full_name?.substring(0, 2).toUpperCase() || 'AK'}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white truncate">{currentUser?.full_name || ''}</p>
            <p className="text-[11px] text-navy-300 truncate">{currentUser?.department || ''}</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
