import {
  CandlestickSeries,
  type CandlestickData,
  ColorType,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  LineSeries,
  type MouseEventParams,
  type SeriesMarker,
  type SeriesMarkerBar,
  type SeriesMarkerBarPosition,
  type Time,
  createChart,
  createSeriesMarkers,
} from 'lightweight-charts'
import * as React from 'react'

import {
  GROUP_COLOR_VAR,
  type MarkerCluster,
  type MarkerGroup,
  markerText,
} from '@/lib/markers'
import type { PriceBar } from '@/types/api'

export type ChartStyle = 'candles' | 'line'

export interface PriceChartProps {
  bars: PriceBar[]
  clusters: MarkerCluster[]
  style: ChartStyle
  showVolume: boolean
  showMarkers: boolean
  visibleRange: { from: string; to: string } | null
  theme: 'dark' | 'light'
  onSelectClusters: (clusters: MarkerCluster[]) => void
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888'
}

export function timeToIso(time: Time | undefined): string | null {
  if (time === undefined) return null
  if (typeof time === 'string') return time
  if (typeof time === 'number') return new Date(time * 1000).toISOString().slice(0, 10)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${time.year}-${pad(time.month)}-${pad(time.day)}`
}

const POSITION: Record<MarkerGroup, SeriesMarkerBarPosition> = {
  purchase: 'belowBar',
  sale: 'aboveBar',
  exercise: 'belowBar',
  compensation: 'belowBar',
  other: 'aboveBar',
}
const SHAPE: Record<MarkerGroup, SeriesMarker<Time>['shape']> = {
  purchase: 'arrowUp',
  sale: 'arrowDown',
  exercise: 'circle',
  compensation: 'circle',
  other: 'square',
}

export function toSeriesMarkers(clusters: MarkerCluster[]): SeriesMarkerBar<Time>[] {
  return clusters.map((c) => ({
    id: `${c.time}|${c.group}`,
    time: c.time,
    position: POSITION[c.group],
    shape: SHAPE[c.group],
    color: cssVar(GROUP_COLOR_VAR[c.group]),
    text: markerText(c),
    size: c.transactions.length > 5 ? 1.6 : 1.1,
  }))
}

interface Legend {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number | null
}

export function PriceChart(props: PriceChartProps) {
  const { bars, clusters, style, showVolume, showMarkers, visibleRange, theme, onSelectClusters } =
    props
  const container = React.useRef<HTMLDivElement>(null)
  const chartRef = React.useRef<IChartApi | null>(null)
  const mainRef = React.useRef<ISeriesApi<'Candlestick'> | ISeriesApi<'Line'> | null>(null)
  const volumeRef = React.useRef<ISeriesApi<'Histogram'> | null>(null)
  const markersRef = React.useRef<ISeriesMarkersPluginApi<Time> | null>(null)
  const clustersRef = React.useRef(clusters)
  const selectRef = React.useRef(onSelectClusters)
  const [legend, setLegend] = React.useState<Legend | null>(null)

  React.useEffect(() => {
    clustersRef.current = clusters
    selectRef.current = onSelectClusters
  }, [clusters, onSelectClusters])
  const byDate = React.useMemo(() => new Map(bars.map((b) => [b.date, b])), [bars])
  const lastBar = bars.length ? bars[bars.length - 1] : null

  // Create the chart once.
  React.useEffect(() => {
    if (!container.current) return
    const chart = createChart(container.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: cssVar('--muted'),
        fontSize: 11,
        attributionLogo: true,
      },
      grid: {
        vertLines: { color: cssVar('--chart-grid') },
        horzLines: { color: cssVar('--chart-grid') },
      },
      rightPriceScale: { borderColor: cssVar('--border') },
      timeScale: { borderColor: cssVar('--border'), rightOffset: 4 },
      crosshair: { mode: 0 },
    })
    chartRef.current = chart

    const onClick = (param: MouseEventParams<Time>) => {
      const all = clustersRef.current
      if (typeof param.hoveredObjectId === 'string') {
        const hit = all.find((c) => `${c.time}|${c.group}` === param.hoveredObjectId)
        if (hit) {
          selectRef.current([hit])
          return
        }
      }
      const day = timeToIso(param.time)
      if (!day) return
      const hits = all.filter((c) => c.time === day)
      if (hits.length) selectRef.current(hits)
    }
    chart.subscribeClick(onClick)
    return () => {
      chart.unsubscribeClick(onClick)
      chart.remove()
      chartRef.current = null
      mainRef.current = null
      volumeRef.current = null
      markersRef.current = null
    }
  }, [])

  // Theme colours.
  React.useEffect(() => {
    chartRef.current?.applyOptions({
      layout: { textColor: cssVar('--muted') },
      grid: {
        vertLines: { color: cssVar('--chart-grid') },
        horzLines: { color: cssVar('--chart-grid') },
      },
      rightPriceScale: { borderColor: cssVar('--border') },
      timeScale: { borderColor: cssVar('--border') },
    })
    volumeRef.current?.applyOptions({ color: cssVar('--muted') + '55' })
  }, [theme])

  // Price series (recreated when the style changes).
  React.useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    if (mainRef.current) {
      markersRef.current?.detach()
      markersRef.current = null
      chart.removeSeries(mainRef.current)
      mainRef.current = null
    }
    if (style === 'candles') {
      const series = chart.addSeries(CandlestickSeries, {
        upColor: cssVar('--buy'),
        downColor: cssVar('--sell'),
        wickUpColor: cssVar('--buy'),
        wickDownColor: cssVar('--sell'),
        borderVisible: false,
      })
      series.setData(
        bars.map<CandlestickData<Time>>((b) => ({
          time: b.date,
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
        })),
      )
      mainRef.current = series
    } else {
      const series = chart.addSeries(LineSeries, {
        color: cssVar('--foreground'),
        lineWidth: 2,
      })
      series.setData(bars.map((b) => ({ time: b.date, value: b.close })))
      mainRef.current = series
    }
    markersRef.current = createSeriesMarkers(mainRef.current as ISeriesApi<'Line'>, [])
  }, [bars, style, theme])

  // Volume.
  React.useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    if (volumeRef.current) {
      chart.removeSeries(volumeRef.current)
      volumeRef.current = null
    }
    if (!showVolume) return
    const series = chart.addSeries(HistogramSeries, {
      priceScaleId: 'volume',
      priceFormat: { type: 'volume' },
      color: cssVar('--muted') + '55',
      lastValueVisible: false,
      priceLineVisible: false,
    })
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
    series.setData(
      bars.filter((b) => b.volume !== null).map((b) => ({ time: b.date, value: b.volume ?? 0 })),
    )
    volumeRef.current = series
  }, [bars, showVolume])

  // Markers.
  React.useEffect(() => {
    markersRef.current?.setMarkers(showMarkers ? toSeriesMarkers(clusters) : [])
  }, [clusters, showMarkers, style, bars, theme])

  // Visible range.
  React.useEffect(() => {
    const chart = chartRef.current
    if (!chart || !bars.length) return
    if (visibleRange) {
      try {
        chart.timeScale().setVisibleRange({ from: visibleRange.from, to: visibleRange.to })
      } catch {
        chart.timeScale().fitContent()
      }
    } else {
      chart.timeScale().fitContent()
    }
  }, [visibleRange, bars, style])

  // OHLC legend follows the crosshair.
  React.useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const onMove = (param: MouseEventParams<Time>) => {
      const day = timeToIso(param.time)
      const bar = day ? byDate.get(day) : undefined
      setLegend(bar ? { ...bar, volume: bar.volume } : null)
    }
    chart.subscribeCrosshairMove(onMove)
    return () => chart.unsubscribeCrosshairMove(onMove)
  }, [byDate])

  const shown = legend ?? (lastBar ? { ...lastBar } : null)
  const change = shown ? shown.close - shown.open : 0

  return (
    <div className="relative h-full w-full">
      {shown ? (
        <div className="pointer-events-none absolute left-3 top-2 z-10 flex flex-wrap gap-x-3 font-mono text-[11px] text-muted">
          <span className="text-foreground">{shown.date}</span>
          <span>
            O <span className="text-foreground">{shown.open.toFixed(2)}</span>
          </span>
          <span>
            H <span className="text-foreground">{shown.high.toFixed(2)}</span>
          </span>
          <span>
            L <span className="text-foreground">{shown.low.toFixed(2)}</span>
          </span>
          <span>
            C{' '}
            <span className={change >= 0 ? 'text-buy' : 'text-sell'}>{shown.close.toFixed(2)}</span>
          </span>
          {shown.volume !== null ? (
            <span>
              V <span className="text-foreground">{Math.round(shown.volume).toLocaleString()}</span>
            </span>
          ) : null}
        </div>
      ) : null}
      <div ref={container} className="h-full w-full" data-testid="price-chart" />
    </div>
  )
}
