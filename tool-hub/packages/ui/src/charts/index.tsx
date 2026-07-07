"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "../components/card";
import { chartColors } from "../tokens";

type ChartCardProps = {
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
};

function ChartCard({ title, description, children, className }: ChartCardProps) {
  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-semibold">{title}</CardTitle>
        {description ? <p className="text-xs text-text-secondary mt-1">{description}</p> : null}
      </CardHeader>
      <CardContent className="h-64">{children}</CardContent>
    </Card>
  );
}

export function HorizontalBarChartCard({
  title,
  description,
  data,
  dataKey = "score",
  nameKey = "domain",
}: {
  title: string;
  description?: string;
  data: Array<Record<string, string | number>>;
  dataKey?: string;
  nameKey?: string;
}) {
  return (
    <ChartCard title={title} description={description}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--border)" />
          <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey={nameKey} width={120} tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey={dataKey} fill={chartColors.primary} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function DonutChartCard({
  title,
  description,
  data,
}: {
  title: string;
  description?: string;
  data: Array<{ name: string; value: number }>;
}) {
  const colors = [chartColors.success, chartColors.warning, chartColors.danger, chartColors.muted];
  return (
    <ChartCard title={title} description={description}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={2}>
            {data.map((_, i) => (
              <Cell key={i} fill={colors[i % colors.length]} />
            ))}
          </Pie>
          <Tooltip />
        </PieChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function FunnelBarChartCard({
  title,
  description,
  data,
}: {
  title: string;
  description?: string;
  data: Array<{ stage: string; count: number }>;
}) {
  return (
    <ChartCard title={title} description={description}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
          <XAxis dataKey="stage" tick={{ fontSize: 11 }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="count" fill={chartColors.secondary} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function RadarChartCard({
  title,
  description,
  data,
  dataKey = "value",
  nameKey = "signal",
}: {
  title: string;
  description?: string;
  data: Array<Record<string, string | number>>;
  dataKey?: string;
  nameKey?: string;
}) {
  return (
    <ChartCard title={title} description={description}>
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid />
          <PolarAngleAxis dataKey={nameKey} tick={{ fontSize: 10 }} />
          <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 9 }} />
          <Radar dataKey={dataKey} stroke={chartColors.primary} fill={chartColors.primary} fillOpacity={0.35} />
          <Tooltip />
        </RadarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function LineTrendChartCard({
  title,
  description,
  data,
  dataKey = "value",
  nameKey = "label",
}: {
  title: string;
  description?: string;
  data: Array<Record<string, string | number>>;
  dataKey?: string;
  nameKey?: string;
}) {
  return (
    <ChartCard title={title} description={description}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey={nameKey} tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Line type="monotone" dataKey={dataKey} stroke={chartColors.primary} strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
