// 管理看板 — 运营统计（总览 / 趋势 / 聚合）
import { ReloadOutlined } from '@ant-design/icons'
import {
  App as AntApp,
  Button,
  DatePicker,
  Spin,
} from 'antd'
import type { Dayjs } from 'dayjs'
import dayjs from 'dayjs'
import {
  ArcElement,
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'
import type { ChartData, ChartOptions } from 'chart.js'
import { Doughnut, Line } from 'react-chartjs-2'
import { useEffect, useMemo, useState } from 'react'
import {
  fetchAdminAggregation,
  fetchAdminOverview,
  fetchAdminTrend,
  type AdminAggregation,
  type AdminOverview,
  type AdminTrend,
} from './api'

// 注册 Chart.js 所需组件
ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, ArcElement, Tooltip, Legend, Filler)

// 模型类型与配色（与后端 llm_call_logs.model_type 对应）
const MODEL_TYPES = ['chat', 'embedding', 'rerank'] as const
const MODEL_COLORS: Record<string, string> = {
  chat: '#6366f1',
  embedding: '#22c55e',
  rerank: '#f59e0b',
}

interface AdminPanelProps {
  isDark: boolean
}

// 指标卡配置
interface MetricItem {
  label: string
  value: string
  unit?: string
  unitPos?: 'pre' | 'post' // 单位显示位置，默认前缀
  accent?: boolean
}

export default function AdminPanel({ isDark }: AdminPanelProps) {
  const { message } = AntApp.useApp()

  // 日期范围：默认最近 7 天
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null]>([
    dayjs().subtract(6, 'day'),
    dayjs(),
  ])
  const [overview, setOverview] = useState<AdminOverview | null>(null)
  const [trendDays, setTrendDays] = useState<AdminTrend['days']>([])
  const [aggregation, setAggregation] = useState<AdminAggregation | null>(null)
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false) // 是否完成过首次加载

  // 并发拉取三个统计接口
  async function loadData() {
    setLoading(true)
    try {
      const from = range[0]?.format('YYYY-MM-DD')
      const to = range[1]?.format('YYYY-MM-DD')
      const [ov, trend, agg] = await Promise.all([
        fetchAdminOverview(from, to),
        fetchAdminTrend(from, to),
        fetchAdminAggregation(from, to),
      ])
      setOverview(ov)
      setTrendDays(trend.days || [])
      setAggregation(agg)
      setLoaded(true)
    } catch {
      message.error('统计数据加载失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  // 挂载时加载一次
  useEffect(() => {
    void loadData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 主题相关的图表配色
  const chartTheme = useMemo(() => {
    const light = isDark
      ? {
          grid: 'rgba(255,255,255,0.08)',
          ticks: '#9aa4b2',
          legend: '#b8c0cc',
          tooltipBg: '#1e2430',
          tooltipText: '#e5e9f0',
          tooltipBorder: 'rgba(255,255,255,0.12)',
        }
      : {
          grid: '#f0f0f5',
          ticks: '#8f99a8',
          legend: '#5f6b7a',
          tooltipBg: '#ffffff',
          tooltipText: '#1a1d23',
          tooltipBorder: '#e8e8f0',
        }
    return light
  }, [isDark])

  // 趋势图公共选项
  const lineOptions = useMemo<ChartOptions<'line'>>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'bottom',
          labels: { boxWidth: 10, padding: 15, color: chartTheme.legend, usePointStyle: true, font: { size: 11 } },
        },
        tooltip: {
          backgroundColor: chartTheme.tooltipBg,
          titleColor: chartTheme.tooltipText,
          bodyColor: chartTheme.tooltipText,
          borderColor: chartTheme.tooltipBorder,
          borderWidth: 1,
          cornerRadius: 8,
          padding: 10,
        },
      },
      scales: {
        x: {
          grid: { color: chartTheme.grid },
          ticks: { color: chartTheme.ticks, maxRotation: 45, font: { size: 10 } },
        },
        y: {
          grid: { color: chartTheme.grid },
          ticks: {
            color: chartTheme.ticks,
            beginAtZero: true,
            font: { size: 10 },
            callback: v => (Number(v) >= 1000 ? `${Math.round(Number(v) / 1000)}K` : v),
          },
        },
      },
    }),
    [chartTheme],
  )

  // 成本走势：每日总成本
  const costChart = useMemo<ChartData<'line'>>(() => {
    const labels = trendDays.map(d => d.date)
    const totalCost = trendDays.map(d => {
      let sum = 0
      for (const t of MODEL_TYPES) sum += (d.models[t]?.cost || 0)
      return Number(sum.toFixed(4))
    })
    return {
      labels,
      datasets: [
        {
          label: '总成本',
          data: totalCost,
          borderColor: '#6366f1',
          backgroundColor: isDark ? 'rgba(99,102,241,0.18)' : 'rgba(99,102,241,0.08)',
          fill: true,
          tension: 0.3,
          pointRadius: 3,
          pointHoverRadius: 6,
          pointBackgroundColor: '#6366f1',
        },
      ],
    }
  }, [trendDays, isDark])

  // Token 用量分布：按模型堆叠（input tokens）
  const tokenChart = useMemo<ChartData<'line'>>(() => {
    const labels = trendDays.map(d => d.date)
    const datasets = MODEL_TYPES.map(t => ({
      label: t,
      data: trendDays.map(d => d.models[t]?.input_tokens || 0),
      borderColor: MODEL_COLORS[t],
      backgroundColor: `${MODEL_COLORS[t]}${isDark ? '33' : '1a'}`,
      fill: true,
      tension: 0.3,
      pointRadius: 2,
      pointHoverRadius: 5,
    }))
    return { labels, datasets }
  }, [trendDays, isDark])

  // 模型开销构成：各模型成本汇总占比
  const modelPie = useMemo<ChartData<'doughnut'>>(() => {
    const total: Record<string, number> = {}
    for (const d of trendDays) {
      for (const t of MODEL_TYPES) total[t] = (total[t] || 0) + (d.models[t]?.cost || 0)
    }
    return {
      labels: MODEL_TYPES.map(t => t),
      datasets: [
        {
          data: MODEL_TYPES.map(t => Number(total[t]?.toFixed(4) || 0)),
          backgroundColor: MODEL_TYPES.map(t => MODEL_COLORS[t]),
          borderColor: isDark ? '#171c26' : '#ffffff',
          borderWidth: 3,
        },
      ],
    }
  }, [trendDays, isDark])

  const doughnutOptions = useMemo<ChartOptions<'doughnut'>>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: { boxWidth: 10, padding: 12, color: chartTheme.legend, usePointStyle: true, font: { size: 11 } },
        },
        tooltip: {
          backgroundColor: chartTheme.tooltipBg,
          titleColor: chartTheme.tooltipText,
          bodyColor: chartTheme.tooltipText,
          borderColor: chartTheme.tooltipBorder,
          borderWidth: 1,
          cornerRadius: 8,
          padding: 10,
        },
      },
    }),
    [chartTheme],
  )

  // 指标卡数值
  const metrics: MetricItem[] = useMemo(() => {
    if (!overview) return []
    return [
      { label: '活跃用户', value: String(overview.active_users), accent: true },
      { label: '活跃会话', value: String(overview.active_sessions), accent: true },
      { label: '总调用次数', value: overview.total_calls.toLocaleString(), accent: true },
      { label: '总成本', value: overview.total_cost.toFixed(2), unit: '¥' },
      { label: '错误数', value: String(overview.error_count) },
      { label: '平均延迟', value: String(overview.avg_latency_ms), unit: 'ms', unitPos: 'post' },
    ]
  }, [overview])

  const empty = loaded && trendDays.length === 0

  return (
    <div className="admin-wrap">
      {/* 工具栏 */}
      <div className="admin-toolbar">
        <span className="admin-title">运营统计</span>
        <DatePicker.RangePicker
          value={range}
          onChange={d => {
            if (d && d[0] && d[1]) {
              setRange([d[0], d[1]])
            }
          }}
          allowClear={false}
        />
        <Button icon={<ReloadOutlined />} onClick={() => void loadData()} loading={loading}>
          刷新数据
        </Button>
      </div>

      <Spin spinning={loading && !loaded} tip="加载中…">
        {/* 指标卡区 */}
        {metrics.length > 0 && (
          <div className="admin-metrics">
            {metrics.map(m => (
              <div className="admin-metric-card" key={m.label}>
                <div className="admin-metric-label">{m.label}</div>
                <div className={`admin-metric-value ${m.accent ? 'accent' : ''}`}>
                  {m.unitPos !== 'post' && m.unit && <span className="admin-metric-unit">{m.unit}</span>}
                  {m.value}
                  {m.unitPos === 'post' && m.unit && <span className="admin-metric-unit">{m.unit}</span>}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 图表区 */}
        {!empty && (
          <div className="admin-charts">
            <div className="admin-chart-panel full">
              <div className="admin-panel-title"><span className="dot" />调用成本走势</div>
              <div className="admin-chart-canvas"><Line data={costChart} options={lineOptions} /></div>
            </div>
            <div className="admin-chart-panel">
              <div className="admin-panel-title"><span className="dot" />Token 用量分布</div>
              <div className="admin-chart-canvas"><Line data={tokenChart} options={lineOptions} /></div>
            </div>
            <div className="admin-chart-panel">
              <div className="admin-panel-title"><span className="dot" />模型开销构成</div>
              <div className="admin-chart-canvas"><Doughnut data={modelPie} options={doughnutOptions} /></div>
            </div>
          </div>
        )}

        {/* 空态 */}
        {empty && <div className="admin-empty">所选时间段暂无调用数据</div>}

        {/* 综合指标 */}
        {aggregation && (
          <div className="admin-agg">
            <div className="admin-agg-col">
              <div className="admin-agg-head">人均指标</div>
              <AggCard label="平均调用" value={aggregation.per_user.avg_calls} unit="次" />
              <AggCard label="平均输入 Token" value={fmtNum(aggregation.per_user.avg_input_tokens)} unit="tok" />
              <AggCard label="平均输出 Token" value={fmtNum(aggregation.per_user.avg_output_tokens)} unit="tok" />
              <AggCard label="平均成本" value={aggregation.per_user.avg_cost.toFixed(4)} unit="¥" />
              <AggCard label="平均延迟" value={String(aggregation.per_user.avg_latency_ms)} unit="ms" />
            </div>
            <div className="admin-agg-col">
              <div className="admin-agg-head">每会话指标</div>
              <AggCard label="平均调用" value={aggregation.per_session.avg_calls} unit="次" />
              <AggCard label="平均输入 Token" value={fmtNum(aggregation.per_session.avg_input_tokens)} unit="tok" />
              <AggCard label="平均输出 Token" value={fmtNum(aggregation.per_session.avg_output_tokens)} unit="tok" />
              <AggCard label="平均成本" value={aggregation.per_session.avg_cost.toFixed(4)} unit="¥" />
              <AggCard label="平均延迟" value={String(aggregation.per_session.avg_latency_ms)} unit="ms" />
            </div>
          </div>
        )}
      </Spin>
    </div>
  )
}

// 千分位格式化
function fmtNum(n: number): string {
  return n.toLocaleString()
}

// 聚合指标单项卡片
function AggCard({ label, value, unit }: { label: string; value: string | number; unit: string }) {
  return (
    <div className="admin-agg-card">
      <span className="admin-agg-label">{label}</span>
      <span className="admin-agg-value">{value}<span className="admin-agg-unit">{unit}</span></span>
    </div>
  )
}
