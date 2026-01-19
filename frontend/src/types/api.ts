// API Response Types

export interface StatusResponse {
  running: boolean;
  agent_name: string;
  agent_type: string;
  strategy: string;
  dry_run: boolean;
  uptime_seconds: number;
  loop_count: number;
  last_observation: string | null;
  balance: number;
  positions_count: number;
}

export interface PerformanceResponse {
  current_capital: number;
  initial_capital: number;
  total_return: number;
  total_return_pct: number;
  total_pnl: number;
  daily_pnl: number;
  win_rate: number;
  total_trades: number;
}

export interface Position {
  market_id: string;
  size: number;
  outcome: string;
  avg_price: number;
  current_price: number;
  pnl: number;
}

export interface PositionExposure {
  market_id: string;
  market_question: string;
  outcome: string;
  size: number;
  entry_price: number;
  current_price: number;
  value: number;
  pnl: number;
  pnl_pct: number;
  correlation_group: string | null;
  has_trailing_stop: boolean;
  stop_price: number | null;
}

export interface CorrelationGroup {
  group_name: string;
  total_exposure: number;
  positions_count: number;
  markets: string[];
  risk_level: 'low' | 'medium' | 'high';
}

export interface ExposureResponse {
  total_value: number;
  total_exposure: number;
  cash_balance: number;
  positions: PositionExposure[];
  correlation_groups: CorrelationGroup[];
  exposure_by_category: Record<string, number>;
  risk_metrics: {
    concentration_ratio: number;
    position_count: number;
    avg_position_size: number;
    max_position_size: number;
    exposure_pct: number;
    daily_pnl: number;
    daily_loss_limit_used: number;
  };
  warnings: string[];
}

export interface Trade {
  id: number;
  order_id: string | null;
  market_id: string;
  market_name?: string;
  outcome: string;
  side: string;
  size: number;
  price: number;
  status: string;
  timestamp: string;
  realized_pnl: number | null;
}

export interface WebSocketMessage {
  type: 'status' | 'trade' | 'position' | 'alert';
  data: unknown;
}
