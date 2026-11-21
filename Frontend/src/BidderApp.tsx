import { useState } from 'react';
import BidderSidebar from '@/components/BidderSidebar';
import Header from '@/components/Header';
import BidderDashboard from '@/pages/BidderDashboard';
import BidderTendersPage from '@/pages/BidderTendersPage';
import VerificationTable from '@/components/VerificationTable';
import DocumentsTable from '@/components/DocumentsTable';
import BidSubmissionModal from '@/components/BidSubmissionModal';
import BidderAlertsPage from '@/pages/BidderAlertsPage';
import SupportPage from '@/pages/SupportPage';
import SettingsPage from '@/pages/SettingsPage';

interface BidderAppProps {
  currentUser: any;
  onLogout: () => void;
}

export default function BidderApp({ currentUser, onLogout }: BidderAppProps) {
  const [currentTab, setCurrentTab] = useState<string>('dashboard');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [selectedTender, setSelectedTender] = useState<any>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);

  const renderContent = () => {
    switch (currentTab) {
      case 'dashboard':
        return <BidderDashboard key={`dashboard-${refreshVersion}`} currentUser={currentUser} onNavigate={(tab: string) => setCurrentTab(tab)} onOpenTender={(t) => { setSelectedTender(t); setIsModalOpen(true); }} />;
      case 'tenders':
        return (
          <BidderTendersPage 
            searchTerm={searchTerm} 
            onOpenBid={(tender) => {
              setSelectedTender(tender);
              setIsModalOpen(true);
            }} 
          />
        );
      case 'bids':
        return <VerificationTable key={`bids-${refreshVersion}`} searchTerm={searchTerm} currentUser={currentUser} listMode="bids" />;
      case 'documents':
        return <DocumentsTable
          key={`documents-${refreshVersion}`}
          searchTerm={searchTerm}
          onStartBid={() => setCurrentTab('tenders')}
        />;
      case 'alerts':
        return <BidderAlertsPage />;
      case 'support':
        return <SupportPage currentUser={currentUser} />;
      case 'settings':
        return <SettingsPage />;
      default:
        return <BidderDashboard />;
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex">
      <BidderSidebar
        currentTab={currentTab}
        currentUser={currentUser}
        onOpenNewBid={() => {
          setSelectedTender(null);
          setIsModalOpen(false);
          setCurrentTab('tenders');
        }}
        onTabChange={(tab) => {
          if (tab === 'logout') {
            onLogout();
          } else {
            setCurrentTab(tab);
          }
        }}
      />
      <div className="flex h-screen min-w-0 flex-1 flex-col overflow-hidden">
        <Header 
          searchTerm={searchTerm} 
          onSearchChange={setSearchTerm} 
          currentUser={currentUser} 
          currentTab={currentTab}
          onLogout={onLogout}
        />
        <main className="flex-1 overflow-y-auto px-4 py-5 pb-8 md:px-8 md:py-8">
          <div className="mx-auto w-full max-w-[1440px]">
            {renderContent()}
          </div>
        </main>
      </div>
      <BidSubmissionModal 
        isOpen={isModalOpen}
        selectedTender={selectedTender}
        onClose={() => {
          setIsModalOpen(false);
          setSelectedTender(null);
        }} 
        onSuccess={() => {
          setRefreshVersion((version) => version + 1);
          setIsModalOpen(false);
          setSelectedTender(null);
        }}
      />
    </div>
  );
}
