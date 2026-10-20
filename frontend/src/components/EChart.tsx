import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption, EChartsType } from 'echarts'
import { useEffect, useRef } from 'react'

/**
 * ECharts 轻封装（M6 统计页用）。
 *
 * 两个刻意的选择：
 * 1. **按需注册**（只用柱/折线/饼 + 提示/图例/网格）而不是 `import * as echarts from 'echarts'`：
 *    全量包会往懒加载 chunk 里塞 1.1 MB，按需后不到三分之一
 * 2. 自己写这 20 行，不引 `echarts-for-react`：只需要
 *    「挂载 → setOption → 跟随容器 resize → 卸载销毁」这一条路径
 */
echarts.use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
])

export default function EChart({
  option,
  height = 280,
}: {
  option: EChartsOption
  height?: number
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<EChartsType | null>(null)

  useEffect(() => {
    const element = containerRef.current
    if (!element) return

    const chart = echarts.init(element)
    chartRef.current = chart

    // 侧边栏收起 / 窗口缩放都要跟着变，用 ResizeObserver 比监听 window.resize 准
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(element)

    return () => {
      observer.disconnect()
      chart.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    // notMerge=true：切换时间范围时旧 series 不残留
    chart.setOption(option, true)
    // Flex/Grid 布局里容器尺寸可能异步确定，setOption 后补一次 resize，
    // 否则 canvas 会停在错误尺寸/偏移（大屏下表现成「浮动」）
    requestAnimationFrame(() => chart.resize())
  }, [option])

  return <div ref={containerRef} style={{ width: '100%', height }} />
}
