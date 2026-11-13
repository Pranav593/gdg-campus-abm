export type Weekday = 'Monday' | 'Tuesday' | 'Wednesday' | 'Thursday' | 'Friday'

export type Building = {
  code: string
  full_name: string
  lat: number
  lon: number
  status: string
}

export type CampusPrediction = {
  building_code: string
  predicted_occupancy: number
}

export type CampusPredictionResponse = {
  weekday: string
  time: string
  semester_week: number
  predictions: CampusPrediction[]
}

const API_BASE_URL = (import.meta.env.VITE_OCCUPANCY_API_BASE_URL || '').replace(/\/$/, '')

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function validateResponse(value: unknown): CampusPredictionResponse {
  if (!isRecord(value) || !Array.isArray(value.predictions) || value.predictions.length !== 35) {
    throw new Error('The occupancy API returned an invalid 35-building response.')
  }
  const predictions = value.predictions.map((item) => {
    if (!isRecord(item) || typeof item.building_code !== 'string' ||
        typeof item.predicted_occupancy !== 'number' || !Number.isFinite(item.predicted_occupancy) ||
        item.predicted_occupancy < 0) {
      throw new Error('The occupancy API returned an invalid prediction value.')
    }
    return { building_code: item.building_code, predicted_occupancy: item.predicted_occupancy }
  })
  if (typeof value.weekday !== 'string' || typeof value.time !== 'string' || typeof value.semester_week !== 'number') {
    throw new Error('The occupancy API returned an invalid request echo.')
  }
  return { weekday: value.weekday, time: value.time, semester_week: value.semester_week, predictions }
}

export async function fetchCampusPredictions(
  weekday: Weekday,
  time: string,
  week: number,
  signal: AbortSignal,
): Promise<CampusPredictionResponse> {
  const url = new URL(`${API_BASE_URL}/api/predict/campus`)
  url.searchParams.set('weekday', weekday)
  url.searchParams.set('time', time)
  url.searchParams.set('week', String(week))
  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error(`Occupancy API unavailable (${response.status}).`)
  return validateResponse(await response.json())
}
