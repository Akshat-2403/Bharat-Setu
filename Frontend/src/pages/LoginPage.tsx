import { useEffect, useState } from 'react';
import { ShieldCheck, Lock, Mail, ArrowRight, Building2, User as UserIcon, CreditCard, FileCheck, Eye, EyeOff, LoaderCircle, AlertCircle } from 'lucide-react';
import { loginApi, registerApi } from '@/services/api';
import { LanguageSelector, useTranslation } from '@/i18n';

interface LoginPageProps {
  onLoginSuccess: (user: any) => void;
  initialNotice?: string;
}

export default function LoginPage({ onLoginSuccess, initialNotice }: LoginPageProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<'login' | 'register'>('login');

  // Login form state
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showRegistrationPassword, setShowRegistrationPassword] = useState(false);

  // Register form state
  const [regFullName, setRegFullName] = useState('');
  const [regCompanyName, setRegCompanyName] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regPan, setRegPan] = useState('');
  const [regGstin, setRegGstin] = useState('');

  const [loading, setLoading] = useState(false);
  const [slowRequest, setSlowRequest] = useState(false);
  const [error, setError] = useState(initialNotice || '');

  useEffect(() => {
    if (!loading) {
      setSlowRequest(false);
      return;
    }
    const timer = window.setTimeout(() => setSlowRequest(true), 4500);
    return () => window.clearTimeout(timer);
  }, [loading]);

  const setDemoCredentials = (role: 'officer' | 'bidder' | 'admin') => {
    setError('');
    if (role === 'officer') {
      setEmail('officer@bharatsetu.gov.in');
      setPassword('officer123');
    } else if (role === 'bidder') {
      setEmail('bidder@bharatsetu.gov.in');
      setPassword('bidder123');
    } else {
      setEmail('admin@bharatsetu.gov.in');
      setPassword('admin123');
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const data = await loginApi(email, password);
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('user', JSON.stringify(data.user));
      onLoginSuccess(data.user);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (!err?.response || err.response.status >= 500) {
        setError(t('backendUnavailable'));
      } else if (err.response.status === 401 && detail === 'Incorrect email or password') {
        setError(t('invalidCredentials'));
      } else {
        setError(typeof detail === 'string' ? detail : t('backendUnavailable'));
      }
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const data = await registerApi({
        email: regEmail,
        password: regPassword,
        full_name: regFullName,
        company_name: regCompanyName,
        pan: regPan || undefined,
        gstin: regGstin || undefined
      });
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('user', JSON.stringify(data.user));
      onLoginSuccess(data.user);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : t('registrationFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#edf2f7] p-4 md:p-8">
      <div className="pointer-events-none absolute -left-28 -top-32 h-96 w-96 rounded-full bg-blue-200/40 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-36 -right-24 h-[30rem] w-[30rem] rounded-full bg-slate-300/40 blur-3xl" />
      <div className="absolute right-4 top-4 z-20 rounded-xl border border-slate-200 bg-white/90 px-3 py-2 shadow-sm md:right-8 md:top-8">
        <LanguageSelector />
      </div>
      <div className="relative z-10 w-full max-w-[510px] rounded-3xl border border-white bg-white p-6 shadow-[0_24px_70px_-28px_rgba(15,43,72,0.28)] md:p-10">
        <div className="flex items-center gap-3 mb-6 justify-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-navy-900 shadow-md">
            <ShieldCheck className="w-7 h-7 text-white" />
          </div>
          <div>
            <h2 className="text-xl font-semibold tracking-tight text-slate-900">BharatSetu</h2>
            <p className="text-xs font-medium text-slate-500">GeM bid compliance workspace</p>
          </div>
        </div>

        {/* Tab Switcher */}
        <div className="mb-6 flex rounded-xl border border-slate-200 bg-slate-50 p-1">
          <button
            type="button"
            onClick={() => { setMode('login'); setError(''); }}
            className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all ${
              mode === 'login'
                ? 'bg-white text-navy-900 shadow-sm ring-1 ring-slate-200'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {t('signIn')}
          </button>
          <button
            type="button"
            onClick={() => { setMode('register'); setError(''); }}
            className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all ${
              mode === 'register'
                ? 'bg-white text-navy-900 shadow-sm ring-1 ring-slate-200'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {t('registerAsBidder')}
          </button>
        </div>

        <h3 className="text-base font-bold text-slate-800 text-center mb-1">
          {mode === 'login' ? t('accessProcurementConsole') : t('newBidderRegistration')}
        </h3>
        <p className="text-xs text-slate-400 text-center mb-6">
          {mode === 'login'
            ? t('signInAsRoles')
            : t('createVendorIdentity')}
        </p>

        {error && (
          <div role="alert" className="mb-4 flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm font-medium text-rose-800">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}

        {slowRequest && !error && (
          <div role="status" className="mb-4 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">
            <LoaderCircle className="mt-0.5 h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
            <span>{t('backendWaking')}</span>
          </div>
        )}

        {mode === 'login' ? (
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label htmlFor="login-email" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-700">{t('emailAddress')}</label>
              <div className="relative">
                <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="email"
                  id="login-email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white py-3 pl-10 pr-4 text-sm text-slate-900 placeholder:text-slate-400 focus:border-navy-600 focus:bg-white focus:ring-2 focus:ring-navy-200"
                />
              </div>
            </div>

            <div>
              <label htmlFor="login-password" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-700">{t('password')}</label>
              <div className="relative">
                <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  id="login-password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white py-3 pl-10 pr-12 text-sm text-slate-900 placeholder:text-slate-400 focus:border-navy-600 focus:ring-2 focus:ring-navy-200"
                />
                <button type="button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? t('hidePassword') : t('showPassword')} className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-800">
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="bs-button-primary w-full py-3.5"
            >
              {loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
              {loading ? t('authenticating') : t('signInToConsole')}
            </button>

            {/* Quick Demo Credentials */}
            {import.meta.env.DEV && <div className="mt-5 border-t border-slate-100 pt-4">
              <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider text-center mb-2">{t('quickDemoAccess')}</p>
              <div className="grid grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={() => setDemoCredentials('officer')}
                  className="px-2 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-xs font-semibold"
                >
                  {t('officer')}
                </button>
                <button
                  type="button"
                  onClick={() => setDemoCredentials('bidder')}
                  className="px-2 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-xs font-semibold"
                >
                  {t('bidder')}
                </button>
                <button
                  type="button"
                  onClick={() => setDemoCredentials('admin')}
                  className="px-2 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-xs font-semibold"
                >
                  {t('admin')}
                </button>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center text-[10px] text-slate-500">
                <span>{t('roleOfficer')}</span>
                <span>{t('roleBidder')}</span>
                <span>{t('roleAdmin')}</span>
              </div>
            </div>}
          </form>
        ) : (
          <form onSubmit={handleRegister} className="space-y-3">
            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase mb-1">{t('companyEntityName')}</label>
              <div className="relative">
                <Building2 className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  required
                  placeholder="e.g. Apex Industrial Solutions Ltd"
                  value={regCompanyName}
                  onChange={(e) => setRegCompanyName(e.target.value)}
                  className="w-full pl-9 pr-4 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:ring-2 focus:ring-navy-400"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase mb-1">{t('authorizedContactName')}</label>
              <div className="relative">
                <UserIcon className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  required
                  placeholder="e.g. Rajesh Sharma"
                  value={regFullName}
                  onChange={(e) => setRegFullName(e.target.value)}
                  className="w-full pl-9 pr-4 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:ring-2 focus:ring-navy-400"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase mb-1">{t('panNumber')}</label>
                <div className="relative">
                  <CreditCard className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    maxLength={10}
                    placeholder="AAAAA1234A"
                    value={regPan}
                    onChange={(e) => setRegPan(e.target.value.toUpperCase())}
                    className="w-full pl-9 pr-2 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:ring-2 focus:ring-navy-400 font-mono uppercase"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase mb-1">{t('gstinNumber')}</label>
                <div className="relative">
                  <FileCheck className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    maxLength={15}
                    placeholder="33AAAAA1234A1Z5"
                    value={regGstin}
                    onChange={(e) => setRegGstin(e.target.value.toUpperCase())}
                    className="w-full pl-9 pr-2 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:ring-2 focus:ring-navy-400 font-mono uppercase"
                  />
                </div>
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase mb-1">{t('officialBusinessEmail')}</label>
              <div className="relative">
                <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="email"
                  required
                  placeholder="procurement@company.com"
                  value={regEmail}
                  onChange={(e) => setRegEmail(e.target.value)}
                  className="w-full pl-9 pr-4 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:ring-2 focus:ring-navy-400"
                />
              </div>
            </div>

            <div>
              <label htmlFor="registration-password" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-700">{t('passwordMinimum')}</label>
              <div className="relative">
                <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type={showRegistrationPassword ? 'text' : 'password'}
                  id="registration-password"
                  autoComplete="new-password"
                  required
                  minLength={6}
                  placeholder="••••••••"
                  value={regPassword}
                  onChange={(e) => setRegPassword(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white py-3 pl-10 pr-12 text-sm focus:border-navy-600 focus:ring-2 focus:ring-navy-200"
                />
                <button type="button" onClick={() => setShowRegistrationPassword((value) => !value)} aria-label={showRegistrationPassword ? t('hidePassword') : t('showPassword')} className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-800">
                  {showRegistrationPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-3 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-bold shadow-md transition-all disabled:opacity-50 mt-2"
            >
              {loading ? t('registeringVendor') : t('createBidderAccount')}
              <ArrowRight className="w-4 h-4" />
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
