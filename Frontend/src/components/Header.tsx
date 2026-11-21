import { useState, useEffect, useRef, useMemo } from 'react';
import { Search, Bell, Calendar, ChevronDown, ShieldAlert, Check, CheckCircle2, LogOut, UserRound } from 'lucide-react';
import { fetchNotifications, markNotificationRead, markAllNotificationsRead, fetchUnreadNotificationCount } from '@/services/api';
import { LanguageSelector, translateNotification, useTranslation } from '@/i18n';

interface HeaderProps {
  searchTerm?: string;
  onSearchChange?: (val: string) => void;
  currentUser?: any;
  currentTab?: string;
  onLogout?: () => void;
}

export default function Header({ searchTerm = '', onSearchChange, currentUser, currentTab = 'dashboard', onLogout }: HeaderProps) {
  const { t } = useTranslation();
  const [notifications, setNotifications] = useState<any[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [showDropdown, setShowDropdown] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const [showAccountMenu, setShowAccountMenu] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const accountRef = useRef<HTMLDivElement>(null);
  const pageTitle = currentUser?.role === 'BIDDER'
    ? ({ dashboard: t('dashboard'), tenders: t('tenderFinder'), bids: t('myBids'), documents: t('myDocuments'), alerts: t('complianceAlerts'), support: t('help'), settings: t('settings') }[currentTab] || t('dashboard'))
    : ({ dashboard: t('dashboard'), queue: t('verificationQueue'), tenders: t('tenders'), reviewed: t('reviewedBids'), vendors: t('vendorRegistry'), flagged: t('flaggedCases'), audit: t('auditHistory'), settings: t('settings'), support: t('helpSupport') }[currentTab] || t('dashboard'));

  const loadNotifications = async () => {
    if (!localStorage.getItem('token')) {
      setNotifications([]);
      setUnreadCount(0);
      return;
    }
    try {
      const data = await fetchNotifications();
      setNotifications(data);
      const countData = await fetchUnreadNotificationCount();
      setUnreadCount(countData.unread_count || 0);
    } catch (e) {
      console.error('Failed to load notifications');
    }
  };

  useEffect(() => {
    loadNotifications();
    const interval = setInterval(loadNotifications, 15000); // poll every 15s
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const clock = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(clock);
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
      if (accountRef.current && !accountRef.current.contains(e.target as Node)) {
        setShowAccountMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleMarkRead = async (id: string) => {
    try {
      await markNotificationRead(id);
      loadNotifications();
    } catch (e) {
      console.error('Failed to mark read');
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
      loadNotifications();
    } catch (e) {
      console.error('Failed to mark all read');
    }
  };

  return (
    <header className="sticky top-0 z-20 flex flex-col justify-between gap-3 border-b border-slate-200 bg-white/95 px-4 py-3 shadow-sm backdrop-blur md:flex-row md:items-center md:px-8 md:py-3.5">
      <div>
        <div className="mb-1 flex items-center gap-2 text-[11px] font-medium text-slate-500 md:text-xs">
          <span>{t('verificationEngine')}</span>
          <span className="text-slate-300">/</span>
          <span className="text-navy-800">{t('procurementOperations')}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2 md:gap-3">
          <h2 className="text-lg font-semibold tracking-tight text-slate-900 md:text-xl">{pageTitle}</h2>
          {/* SIMULATED GOVT VERIFICATION BANNER */}
          <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[10px] font-semibold text-amber-800 md:text-[11px]">
            <ShieldAlert className="w-3.5 h-3.5 text-amber-600 shrink-0" />
            {t('simulatedGovernmentVerification')}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 md:gap-3">
        <div className="hidden sm:block"><LanguageSelector /></div>
        {/* Search */}
        <div className="relative order-last w-full md:order-none md:w-64">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => onSearchChange && onSearchChange(e.target.value)}
            placeholder={`${t('vendor')}, bid ID, GSTIN...`}
            aria-label="Search bids and vendors"
            className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-9 pr-4 text-sm transition-all focus:border-transparent focus:outline-none focus:ring-2 focus:ring-navy-400 md:w-64"
          />
        </div>

        {/* Date */}
        <div className="hidden items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-600 lg:flex">
          <Calendar className="w-4 h-4 text-slate-400" />
          <span>
            {now.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
          </span>
        </div>

        {/* Notifications */}
        <div className="relative" ref={dropdownRef}>
          <button 
            type="button"
            aria-label={`${t('notifications')}${unreadCount ? `, ${unreadCount} unread` : ''}`}
            aria-expanded={showDropdown}
            className="relative rounded-lg p-2 transition-colors hover:bg-slate-100"
            onClick={() => { setShowDropdown(!showDropdown); if (!showDropdown) loadNotifications(); }}
          >
            <Bell className="w-5 h-5 text-slate-600" />
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 w-4 h-4 flex items-center justify-center text-[10px] font-bold text-white bg-red-500 rounded-full ring-2 ring-white">
                {unreadCount}
              </span>
            )}
          </button>

          {showDropdown && (
            <div className="absolute right-0 mt-2 w-[min(20rem,calc(100vw-2rem))] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl z-50">
              <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between bg-slate-50">
                <h3 className="font-bold text-slate-800 text-sm">{t('notifications')}</h3>
                {unreadCount > 0 && (
                  <button 
                    onClick={handleMarkAllRead}
                    className="text-[11px] font-medium text-navy-600 hover:text-navy-700 hover:underline"
                  >
                    {t('markAllRead')}
                  </button>
                )}
              </div>
              <div className="max-h-96 overflow-y-auto">
                {notifications.length === 0 ? (
                  <div className="px-4 py-8 text-center text-sm text-slate-500">
                    {t('noNotifications')}
                  </div>
                ) : (
                  notifications.map((n) => (
                    <div 
                      key={n.id} 
                      className={`px-4 py-3 flex gap-3 border-b border-slate-50 last:border-0 ${!n.is_read ? 'bg-navy-50/30' : 'bg-white'}`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-1">
                                <p className="text-sm font-semibold text-slate-800 truncate">{translateNotification(n, t).title}</p>
                          <span className="text-[10px] text-slate-400 whitespace-nowrap ml-2">
                            {new Date(n.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </div>
                        <p className="text-xs text-slate-600 leading-snug">{translateNotification(n, t).message}</p>
                      </div>
                      {!n.is_read && (
                        <button 
                          onClick={() => handleMarkRead(n.id)}
                          className="shrink-0 w-6 h-6 flex items-center justify-center rounded-full hover:bg-slate-100 text-slate-400 hover:text-navy-600 transition-colors"
                          title={t('markAsRead')}
                        >
                          <Check className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>

        {/* Divider */}
        <div className="w-px h-8 bg-slate-200"></div>

        {/* Session */}
        <div className="relative" ref={accountRef}>
          <button
            type="button"
            aria-label={`Account menu for ${currentUser?.full_name || 'user'}`}
            aria-expanded={showAccountMenu}
            onClick={() => setShowAccountMenu((open) => !open)}
            className="flex min-h-10 items-center gap-2 rounded-lg px-2 py-1.5 text-left transition hover:bg-slate-50"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-navy-100 text-xs font-bold text-navy-900">
              {currentUser?.full_name?.slice(0, 1)?.toUpperCase() || <UserRound className="h-4 w-4" />}
            </span>
            <span className="hidden max-w-36 sm:block">
              <span className="block truncate text-xs font-semibold leading-4 text-slate-800">{currentUser?.full_name || ''}</span>
              <span className="block truncate text-[10px] text-slate-500">{currentUser?.role === 'BIDDER' ? 'Bidder account' : (currentUser?.department || currentUser?.role || '')}</span>
            </span>
            <ChevronDown className="hidden h-4 w-4 text-slate-400 sm:block" />
          </button>
          {showAccountMenu && (
            <div className="absolute right-0 mt-2 w-60 rounded-xl border border-slate-200 bg-white p-2 shadow-xl">
              <p className="truncate px-3 py-2 text-xs font-semibold text-slate-800">{currentUser?.email || currentUser?.full_name}</p>
              <div className="my-1 border-t border-slate-100" />
              <div className="sm:hidden px-3 py-2"><LanguageSelector /></div>
              {onLogout && (
                <button type="button" onClick={onLogout} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-rose-700 hover:bg-rose-50">
                  <LogOut className="h-4 w-4" /> {t('logout')}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
