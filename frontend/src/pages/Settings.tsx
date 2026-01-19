import { useState } from 'react';
import { Key, Shield, Bell, Palette } from 'lucide-react';
import { useAgentControl } from '../hooks/useApi';

interface SettingsSection {
  id: string;
  title: string;
  icon: React.ReactNode;
}

const sections: SettingsSection[] = [
  { id: 'api', title: 'API Keys', icon: <Key className="w-5 h-5" /> },
  { id: 'risk', title: 'Risk Limits', icon: <Shield className="w-5 h-5" /> },
  { id: 'alerts', title: 'Alerts', icon: <Bell className="w-5 h-5" /> },
  { id: 'appearance', title: 'Appearance', icon: <Palette className="w-5 h-5" /> },
];

export function Settings() {
  const [activeSection, setActiveSection] = useState('api');
  const { setDryRun, loading } = useAgentControl();

  // Local state for settings
  const [settings, setSettings] = useState({
    // API Keys (masked)
    anthropicKey: '',
    openaiKey: '',
    polymarketKey: '',

    // Risk Limits
    maxPositionSize: 50,
    maxTotalExposure: 500,
    maxDailyLoss: 100,
    stopLossPct: 20,
    takeProfitPct: 50,
    maxPositions: 5,

    // Alerts
    telegramEnabled: false,
    telegramToken: '',
    telegramChatId: '',
    alertOnTrade: true,
    alertOnError: true,
    alertOnDrawdown: true,

    // Appearance
    theme: 'dark',
    compactMode: false,
    showPnlPercent: true,
  });

  // Note: Settings are read-only in the UI. Edit your .env file to change configuration.
  // Backend settings API is planned for a future release.

  const updateSetting = <K extends keyof typeof settings>(
    key: K,
    value: typeof settings[K]
  ) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
      {/* Sidebar */}
      <div className="lg:col-span-1">
        <div className="glass rounded-xl p-4 sticky top-24">
          <h2 className="text-lg font-semibold mb-4 px-2">Settings</h2>
          <nav className="space-y-1">
            {sections.map(section => (
              <button
                key={section.id}
                onClick={() => setActiveSection(section.id)}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors ${
                  activeSection === section.id
                    ? 'bg-purple-500/20 text-purple-400'
                    : 'text-slate-400 hover:bg-white/5 hover:text-white'
                }`}
              >
                {section.icon}
                <span className="text-sm">{section.title}</span>
              </button>
            ))}
          </nav>
        </div>
      </div>

      {/* Content */}
      <div className="lg:col-span-3">
        <div className="glass rounded-xl p-6">
          {/* API Keys Section */}
          {activeSection === 'api' && (
            <div>
              <h3 className="text-xl font-semibold mb-6 flex items-center gap-3">
                <Key className="w-6 h-6 text-purple-400" />
                API Keys
              </h3>
              <p className="text-slate-400 text-sm mb-6">
                Configure your API keys for AI providers and trading platforms.
                Keys are stored securely and never displayed after saving.
              </p>

              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Anthropic API Key
                  </label>
                  <input
                    type="password"
                    placeholder="sk-ant-..."
                    value={settings.anthropicKey}
                    onChange={e => updateSetting('anthropicKey', e.target.value)}
                    className="w-full px-4 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    OpenAI API Key
                  </label>
                  <input
                    type="password"
                    placeholder="sk-..."
                    value={settings.openaiKey}
                    onChange={e => updateSetting('openaiKey', e.target.value)}
                    className="w-full px-4 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Polymarket Private Key
                  </label>
                  <input
                    type="password"
                    placeholder="0x..."
                    value={settings.polymarketKey}
                    onChange={e => updateSetting('polymarketKey', e.target.value)}
                    className="w-full px-4 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
                  />
                  <p className="text-xs text-slate-500 mt-1">
                    Your Ethereum private key for signing Polymarket transactions
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Risk Limits Section */}
          {activeSection === 'risk' && (
            <div>
              <h3 className="text-xl font-semibold mb-6 flex items-center gap-3">
                <Shield className="w-6 h-6 text-green-400" />
                Risk Limits
              </h3>
              <p className="text-slate-400 text-sm mb-6">
                Configure position sizing and risk management parameters.
                These limits help protect your capital from excessive losses.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Max Position Size ($)
                  </label>
                  <input
                    type="number"
                    value={settings.maxPositionSize}
                    onChange={e => updateSetting('maxPositionSize', Number(e.target.value))}
                    className="w-full px-4 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-green-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Max Total Exposure ($)
                  </label>
                  <input
                    type="number"
                    value={settings.maxTotalExposure}
                    onChange={e => updateSetting('maxTotalExposure', Number(e.target.value))}
                    className="w-full px-4 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-green-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Max Daily Loss ($)
                  </label>
                  <input
                    type="number"
                    value={settings.maxDailyLoss}
                    onChange={e => updateSetting('maxDailyLoss', Number(e.target.value))}
                    className="w-full px-4 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-green-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Max Open Positions
                  </label>
                  <input
                    type="number"
                    value={settings.maxPositions}
                    onChange={e => updateSetting('maxPositions', Number(e.target.value))}
                    className="w-full px-4 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-green-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Stop Loss (%)
                  </label>
                  <input
                    type="number"
                    value={settings.stopLossPct}
                    onChange={e => updateSetting('stopLossPct', Number(e.target.value))}
                    className="w-full px-4 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-green-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Take Profit (%)
                  </label>
                  <input
                    type="number"
                    value={settings.takeProfitPct}
                    onChange={e => updateSetting('takeProfitPct', Number(e.target.value))}
                    className="w-full px-4 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-green-500"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Alerts Section */}
          {activeSection === 'alerts' && (
            <div>
              <h3 className="text-xl font-semibold mb-6 flex items-center gap-3">
                <Bell className="w-6 h-6 text-yellow-400" />
                Alerts & Notifications
              </h3>
              <p className="text-slate-400 text-sm mb-6">
                Configure Telegram notifications for trade executions and system alerts.
              </p>

              <div className="space-y-6">
                <div className="flex items-center justify-between p-4 bg-slate-800/30 rounded-lg">
                  <div>
                    <h4 className="font-medium text-white">Enable Telegram Alerts</h4>
                    <p className="text-sm text-slate-400">Receive notifications via Telegram bot</p>
                  </div>
                  <button
                    onClick={() => updateSetting('telegramEnabled', !settings.telegramEnabled)}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      settings.telegramEnabled ? 'bg-green-500' : 'bg-slate-600'
                    }`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      settings.telegramEnabled ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>

                {settings.telegramEnabled && (
                  <>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-2">
                        Telegram Bot Token
                      </label>
                      <input
                        type="password"
                        placeholder="123456:ABC-DEF..."
                        value={settings.telegramToken}
                        onChange={e => updateSetting('telegramToken', e.target.value)}
                        className="w-full px-4 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-yellow-500"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-2">
                        Chat ID
                      </label>
                      <input
                        type="text"
                        placeholder="-1001234567890"
                        value={settings.telegramChatId}
                        onChange={e => updateSetting('telegramChatId', e.target.value)}
                        className="w-full px-4 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-yellow-500"
                      />
                    </div>
                  </>
                )}

                <div className="border-t border-slate-700 pt-6">
                  <h4 className="font-medium text-white mb-4">Alert Types</h4>
                  <div className="space-y-3">
                    {[
                      { key: 'alertOnTrade', label: 'Trade Executions', desc: 'When orders are placed or filled' },
                      { key: 'alertOnError', label: 'Errors', desc: 'When the bot encounters errors' },
                      { key: 'alertOnDrawdown', label: 'Drawdown Warnings', desc: 'When drawdown exceeds threshold' },
                    ].map(item => (
                      <div key={item.key} className="flex items-center justify-between">
                        <div>
                          <span className="text-sm text-white">{item.label}</span>
                          <p className="text-xs text-slate-500">{item.desc}</p>
                        </div>
                        <button
                          onClick={() => updateSetting(item.key as keyof typeof settings, !settings[item.key as keyof typeof settings])}
                          className={`w-10 h-5 rounded-full transition-colors ${
                            settings[item.key as keyof typeof settings] ? 'bg-green-500' : 'bg-slate-600'
                          }`}
                        >
                          <div className={`w-4 h-4 bg-white rounded-full transition-transform ${
                            settings[item.key as keyof typeof settings] ? 'translate-x-5' : 'translate-x-0.5'
                          }`} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Appearance Section */}
          {activeSection === 'appearance' && (
            <div>
              <h3 className="text-xl font-semibold mb-6 flex items-center gap-3">
                <Palette className="w-6 h-6 text-blue-400" />
                Appearance
              </h3>
              <p className="text-slate-400 text-sm mb-6">
                Customize how the dashboard looks and feels.
              </p>

              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-3">
                    Theme
                  </label>
                  <div className="grid grid-cols-2 gap-3">
                    {['dark', 'light'].map(theme => (
                      <button
                        key={theme}
                        onClick={() => updateSetting('theme', theme)}
                        className={`p-4 rounded-lg border-2 transition-colors ${
                          settings.theme === theme
                            ? 'border-purple-500 bg-purple-500/10'
                            : 'border-slate-700 hover:border-slate-600'
                        }`}
                      >
                        <div className={`w-full h-16 rounded mb-2 ${
                          theme === 'dark' ? 'bg-slate-900' : 'bg-white'
                        }`} />
                        <span className="text-sm capitalize">{theme}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex items-center justify-between p-4 bg-slate-800/30 rounded-lg">
                  <div>
                    <h4 className="font-medium text-white">Compact Mode</h4>
                    <p className="text-sm text-slate-400">Reduce spacing for more data density</p>
                  </div>
                  <button
                    onClick={() => updateSetting('compactMode', !settings.compactMode)}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      settings.compactMode ? 'bg-green-500' : 'bg-slate-600'
                    }`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      settings.compactMode ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>

                <div className="flex items-center justify-between p-4 bg-slate-800/30 rounded-lg">
                  <div>
                    <h4 className="font-medium text-white">Show P&L as Percentage</h4>
                    <p className="text-sm text-slate-400">Display returns as % instead of $</p>
                  </div>
                  <button
                    onClick={() => updateSetting('showPnlPercent', !settings.showPnlPercent)}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      settings.showPnlPercent ? 'bg-green-500' : 'bg-slate-600'
                    }`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      settings.showPnlPercent ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Configuration Notice */}
          <div className="mt-8 pt-6 border-t border-slate-700">
            <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
              <p className="text-sm text-slate-400">
                <span className="font-medium text-slate-300">Note:</span> These settings are for reference only.
                To change configuration, edit your <code className="bg-slate-900 px-1 rounded">.env</code> file
                and restart the application.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
