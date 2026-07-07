export const DEFAULT_WEIGHTS = {
  hiring_demand: 0.3,
  capital_flow: 0.25,
  developer_momentum: 0.2,
  funding_signal: 0.15,
  public_interest: 0.1,
} as const;

export type WeightKey = keyof typeof DEFAULT_WEIGHTS;
