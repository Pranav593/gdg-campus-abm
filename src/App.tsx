import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import buildingsData from './mapping/utd-graph/academic_buildings.json'
import { Building, fetchCampusPredictions, Weekday } from './predictionProvider'

import 'leaflet/dist/leaflet.css'

type OccupancyPoint = Building & { occupancy: number }

const buildings = [
  ...buildingsData.buildings.filter((building) => building.status === 'active' && !building.code.startsWith('Lot') && !building.full_name.includes('Lot') && !['NB', 'NL'].includes(building.code)),
  { code: 'SU', full_name: 'Student Union', lat: 32.986774587571226, lon: -96.74882355333946, status: 'active' },
] as Building[]
const weekdays: Weekday[] = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
const HEATMAP_REFERENCE_OCCUPANCY = 1200
const DAY_START = 420
const DAY_END = 1260

function timeLabel(minutes: number) {
  const hour = Math.floor(minutes / 60)
  const minute = minutes % 60
  return `${hour % 12 || 12}:${minute.toString().padStart(2, '0')} ${hour >= 12 ? 'PM' : 'AM'}`
}

function apiTime(minutes: number) {
  return `${Math.floor(minutes / 60).toString().padStart(2, '0')}:${(minutes % 60).toString().padStart(2, '0')}`
}

function popupMarkup(point: OccupancyPoint, weekday: Weekday, week: number, minutes: number) {
  const activity = point.occupancy >= 900 ? 'High activity' : point.occupancy >= 400 ? 'Moderate activity' : 'Quieter period'
  return `<div class="occupancy-popup"><span class="popup-code">${point.code}</span><strong>${point.full_name}</strong><span class="popup-value">${point.occupancy.toLocaleString()} <small>students</small></span><span class="popup-meta">${weekday} · Week ${week} · ${timeLabel(minutes)}</span><span class="popup-activity">${activity}</span></div>`
}

function Heatmap({
  points, selected, weekday, week, minutes, onSelect,
}: {
  points: OccupancyPoint[]
  selected: OccupancyPoint | null
  weekday: Weekday
  week: number
  minutes: number
  onSelect: (point: OccupancyPoint | null) => void
}) {
  const mapHost = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const map = useRef<L.Map | null>(null)
  const popup = useRef<L.Popup | null>(null)
  const pointsRef = useRef(points)
  const renderRef = useRef<(() => void) | null>(null)
  const onSelectRef = useRef(onSelect)
  pointsRef.current = points
  onSelectRef.current = onSelect

  useEffect(() => {
    if (!mapHost.current || !canvas.current || map.current) return
    const host = mapHost.current
    const canvasElement = canvas.current
    const mapElement = host as HTMLDivElement & { _leaflet_id?: number }
    if (mapElement._leaflet_id) delete mapElement._leaflet_id
    const instance = L.map(host, { zoomControl: false, preferCanvas: true, minZoom: 16, maxZoom: 20 })
    map.current = instance
    L.control.zoom({ position: 'topright' }).addTo(instance)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors', maxZoom: 20,
    }).addTo(instance)
    instance.setView([32.9878, -96.7492], 17.7, { animate: false })

    const render = () => {
      if (!map.current) return
      const width = host.clientWidth
      const height = host.clientHeight
      const density = window.devicePixelRatio || 1
      if (!width || !height) return
      canvasElement.width = width * density
      canvasElement.height = height * density
      canvasElement.style.width = `${width}px`
      canvasElement.style.height = `${height}px`
      const context = canvasElement.getContext('2d')
      if (!context) return
      context.setTransform(density, 0, 0, density, 0, 0)
      context.clearRect(0, 0, width, height)
      pointsRef.current.forEach((point) => {
        if (point.occupancy <= 0) return
        const value = Math.min(100, Math.sqrt(point.occupancy / HEATMAP_REFERENCE_OCCUPANCY) * 100)
        const screen = map.current!.latLngToContainerPoint([point.lat, point.lon])
        const radius = 42 + value * 0.3
        const color = value >= 78 ? '237, 83, 118' : value >= 52 ? '244, 164, 74' : '58, 190, 169'
        const gradient = context.createRadialGradient(screen.x, screen.y, 0, screen.x, screen.y, radius)
        gradient.addColorStop(0, `rgba(${color}, ${Math.min(0.96, 0.56 + value / 250)})`)
        gradient.addColorStop(0.28, `rgba(${color}, ${Math.min(0.68, 0.35 + value / 240)})`)
        gradient.addColorStop(0.7, `rgba(${color}, ${Math.min(0.26, 0.13 + value / 750)})`)
        gradient.addColorStop(1, `rgba(${color}, 0)`)
        context.fillStyle = gradient
        context.fillRect(screen.x - radius, screen.y - radius, radius * 2, radius * 2)
      })
    }

    const selectNearest = (event: L.LeafletMouseEvent) => {
      let nearest: OccupancyPoint | null = null
      let distance = Infinity
      pointsRef.current.forEach((point) => {
        const candidateDistance = instance.distance(event.latlng, [point.lat, point.lon])
        if (candidateDistance < distance) { nearest = point; distance = candidateDistance }
      })
      onSelectRef.current(nearest && distance <= 95 ? nearest : null)
    }

    renderRef.current = render
    instance.on('move zoom resize', render)
    instance.on('click', selectNearest)
    window.addEventListener('resize', render)
    requestAnimationFrame(render)
    return () => {
      window.removeEventListener('resize', render)
      instance.remove()
      map.current = null
      popup.current = null
      canvasElement.width = 0
      canvasElement.height = 0
      renderRef.current = null
      delete mapElement._leaflet_id
    }
  }, [])

  useEffect(() => { requestAnimationFrame(() => renderRef.current?.()) }, [points])

  useEffect(() => {
    if (!map.current) return
    if (!selected) {
      popup.current?.remove()
      popup.current = null
      return
    }
    const content = popupMarkup(selected, weekday, week, minutes)
    if (popup.current) {
      popup.current.setLatLng([selected.lat, selected.lon]).setContent(content)
      return
    }
    popup.current = L.popup({ closeButton: false, closeOnClick: false, className: 'building-popup-shell', offset: [0, -8] })
      .setLatLng([selected.lat, selected.lon])
      .setContent(content)
      .openOn(map.current)
  }, [selected, weekday, week, minutes])

  return <div ref={mapHost} className="map-host" aria-label="Interactive UTD campus occupancy heatmap"><canvas ref={canvas} className="heatmap-canvas" /></div>
}

function App() {
  const [weekday, setWeekday] = useState<Weekday>('Monday')
  const [week, setWeek] = useState(1)
  const [minutes, setMinutes] = useState(480)
  const [requestedMinutes, setRequestedMinutes] = useState(480)
  const [isPlaying, setIsPlaying] = useState(false)
  const [playbackStep, setPlaybackStep] = useState<5 | 30>(5)
  const [predictionMap, setPredictionMap] = useState<Map<string, number> | null>(null)
  const [selectedCode, setSelectedCode] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const requestId = useRef(0)
  const controller = useRef<AbortController | null>(null)
  const predictionCache = useRef(new Map<string, Map<string, number>>())
  const weekdayRef = useRef<Weekday>(weekday)
  const weekRef = useRef(week)

  useEffect(() => { weekdayRef.current = weekday }, [weekday])
  useEffect(() => { weekRef.current = week }, [week])

  useEffect(() => {
    const delay = isPlaying ? 0 : 150
    const timeout = window.setTimeout(() => setRequestedMinutes(minutes), delay)
    return () => window.clearTimeout(timeout)
  }, [minutes, isPlaying])

  useEffect(() => {
    const key = `${weekday}|${week}|${requestedMinutes}`
    const cached = predictionCache.current.get(key)
    if (cached) {
      controller.current?.abort()
      setPredictionMap(cached)
      setLoading(false)
      setError(null)
      return
    }
    const id = ++requestId.current
    controller.current?.abort()
    const nextController = new AbortController()
    controller.current = nextController
    setLoading(true)
    setError(null)
    fetchCampusPredictions(weekday, apiTime(requestedMinutes), week, nextController.signal)
      .then((response) => {
        const coordinates = new Set(buildings.map((building) => building.code))
        const missing = response.predictions.filter((prediction) => !coordinates.has(prediction.building_code)).map((prediction) => prediction.building_code)
        if (missing.length) throw new Error(`No verified coordinates for ${missing.join(', ')}.`)
        const next = new Map(response.predictions.map((prediction) => [prediction.building_code, prediction.predicted_occupancy]))
        if (id !== requestId.current) return
        predictionCache.current.set(key, next)
        setPredictionMap(next)
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === 'AbortError') return
        if (id === requestId.current) {
          setPredictionMap(null)
          setSelectedCode(null)
          setError(reason instanceof Error ? reason.message : 'Unable to load occupancy predictions.')
        }
      })
      .finally(() => { if (id === requestId.current) setLoading(false) })
    return () => nextController.abort()
  }, [weekday, week, requestedMinutes])

  const advanceCalendar = () => {
    const currentIndex = weekdays.indexOf(weekdayRef.current)
    const nextDay = weekdays[(currentIndex + 1) % weekdays.length]
    weekdayRef.current = nextDay
    setWeekday(nextDay)
    if (currentIndex === weekdays.length - 1) {
      const nextWeek = weekRef.current === 15 ? 1 : weekRef.current + 1
      weekRef.current = nextWeek
      setWeek(nextWeek)
    }
  }

  const advanceTimeline = (step: number) => {
    setMinutes((current) => {
      if (current >= DAY_END) {
        advanceCalendar()
        return DAY_START
      }
      return Math.min(DAY_END, current + step)
    })
  }

  useEffect(() => {
    if (!isPlaying) return
    const timer = window.setInterval(() => advanceTimeline(playbackStep), 333)
    return () => window.clearInterval(timer)
  }, [isPlaying, playbackStep])

  const points = useMemo(() => predictionMap ? buildings.flatMap((building) => {
    const occupancy = predictionMap.get(building.code)
    return occupancy === undefined ? [] : [{ ...building, occupancy }]
  }) : [], [predictionMap])
  const selected = selectedCode ? points.find((point) => point.code === selectedCode) || null : null

  const updateTime = (value: number) => { setIsPlaying(false); setMinutes(value) }

  return <main className="map-app">
    <Heatmap points={points} selected={selected} weekday={weekday} week={week} minutes={minutes} onSelect={(point) => setSelectedCode(point?.code || null)} />
    <div className="map-brand"><span className="brand-dot" /><span>UTD <b>occupancy</b></span><em>{loading ? 'loading model…' : error ? 'model unavailable' : 'live model'}</em></div>
    {error && <div className="map-error" role="alert">{error}</div>}
    <aside className="legend" aria-label="Heatmap intensity legend"><span><i className="cool" /> quieter</span><span><i className="warm" /> busier</span></aside>
    <section className="controls" aria-label="Occupancy controls">
      <button className="play-button" aria-label={isPlaying ? 'Pause playback' : 'Play playback'} onClick={() => setIsPlaying((playing) => !playing)}>{isPlaying ? '❚❚' : '▶'}</button>
      <button className="skip-button" aria-label="Skip ahead 30 minutes" title="Skip ahead 30 minutes" onClick={() => { setIsPlaying(false); advanceTimeline(30) }}>+30</button>
      <div className="step-buttons" aria-label="Autoplay interval"><button className={playbackStep === 5 ? 'active' : ''} onClick={() => setPlaybackStep(5)}>5m</button><button className={playbackStep === 30 ? 'active' : ''} onClick={() => setPlaybackStep(30)}>30m</button></div>
      <div className="control-group days"><span className="control-label">Day</span><div className="day-buttons">{weekdays.map((day) => <button key={day} className={weekday === day ? 'active' : ''} onClick={() => { setIsPlaying(false); setWeekday(day) }}>{day.slice(0, 3)}</button>)}</div></div>
      <div className="control-group week"><label htmlFor="week">Week <output>{week}</output></label><input id="week" type="range" min="1" max="15" value={week} onChange={(event) => { setIsPlaying(false); setWeek(Number(event.target.value)) }} /></div>
      <div className="control-group time"><label htmlFor="time">Time <output>{timeLabel(minutes)}</output></label><input id="time" type="range" min={DAY_START} max={DAY_END} step="5" value={minutes} onChange={(event) => updateTime(Number(event.target.value))} /></div>
    </section>
  </main>
}

export default App
