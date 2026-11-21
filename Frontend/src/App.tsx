import { useState, useEffect } from 'react';
import Sidebar from '@/components/Sidebar';
import Header from '@/components/Header';
import MetricsBar from '@/components/MetricsBar';
import VerificationTable from '@/components/VerificationTable';
import AuditFeed from '@/components/AuditFeed';
import BidSubmissionModal from '@/components/BidSubmissionModal';
import LoginPage from '@/pages/LoginPage';
import TendersPage from '@/pages/TendersPage';
import VendorsPage from '@/pages/VendorsPage';
import FlaggedPage from '@/pages/FlaggedPage';
import AuditPage from '@/pages/AuditPage';
import SettingsPage from '@/pages/SettingsPage';
import SupportPage from '@/pages/SupportPage';
import BidderApp from '@/BidderApp';
import { api } from '@/services/api';

function App() {
  const [currentTab, setCurrentTab] = useState<string>('dashboard');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [sessionExpired, setSessionExpired] = useState(false);

  useEffect(() => {
    const handleSessionExpired = () => {
      setSessionExpired(true);
      setCurrentUser(null);
    };
    window.addEventListener('bharatsetu:session-expired', handleSessionExpired);
    return () => window.removeEventListener('bharatsetu:session-expired', handleSessionExpired);
  }, []);

  useEffect(() => {
    const initAuth = async () => {
      const token = localStorage.getItem('token');
      if (!token) {
        setCurrentUser(null);
        return;
      }
      try {
        const res = await api.get('/auth/me');
        const userData = res.data;
        localStorage.setItem('user', JSON.stringify(userData));
        setCurrentUser(userData);
      } catch (e) {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        setCurrentUser(null);
      }
    };
    initAuth();
  }, []);

  if (!currentUser) {
    return <LoginPage onLoginSuccess={(u) => { setSessionExpired(false); setCurrentUser(u); setCurrentTab('dashboard'); }} initialNotice={sessionExpired ? 'Session expired. Please sign in again.' : undefined} />;
  }

  if (currentUser.role === 'BIDDER') {
    return (
      <BidderApp 
        currentUser={currentUser} 
        onLogout={() => {
          localStorage.removeItem('token');
          localStorage.removeItem('user');
          setCurrentUser(null);
          setCurrentTab('login');
        }} 
      />
    );
  }

  const renderContent = () => {
    switch (currentTab) {
      case 'dashboard':
        return (
          <div className="flex flex-col xl:flex-row gap-6">
            <div className="flex-1 min-w-0">
              <MetricsBar />
              <VerificationTable key={`dashboard-${refreshVersion}`} searchTerm={searchTerm} currentUser={currentUser} />
            </div>
            <div className="xl:w-[360px] shrink-0">
              <AuditFeed />
            </div>
          </div>
        );
      case 'queue':
        return <VerificationTable key={`queue-${refreshVersion}`} searchTerm={searchTerm} currentUser={currentUser} />;
      case 'tenders':
        return <TendersPage searchTerm={searchTerm} />;
      case 'vendors':
        return <VendorsPage searchTerm={searchTerm} />;
      case 'flagged':
        return <FlaggedPage searchTerm={searchTerm} />;
      case 'audit':
        return <AuditPage searchTerm={searchTerm} />;
      case 'settings':
        return <SettingsPage />;
      case 'support':
        return <SupportPage currentUser={currentUser} />;
      default:
        return <VerificationTable currentUser={currentUser} />;
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex">
      <Sidebar
        currentTab={currentTab}
        onTabChange={(tab) => {
          if (tab === 'logout') {
            localStorage.removeItem('token');
            localStorage.removeItem('user');
            setCurrentUser(null);
            setCurrentTab('login');
          } else {
            setCurrentTab(tab);
          }
        }}
        onOpenNewBid={() => setIsModalOpen(true)}
        currentUser={currentUser}
      />

      <div className="flex-1 min-w-0 flex flex-col">
        <Header
          searchTerm={searchTerm}
          onSearchChange={setSearchTerm}
          currentUser={currentUser}
        />

        <main className="flex-1 p-6 md:p-8">
          {renderContent()}
        </main>
      </div>

      <BidSubmissionModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSuccess={() => {
          setRefreshVersion((version) => version + 1);
        }}
      />
    </div>
  );
}

export default App;
