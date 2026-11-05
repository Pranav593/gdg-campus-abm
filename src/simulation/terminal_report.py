"""Terminal-only summaries derived from simulation events."""
from collections import defaultdict


def journey_rows(records, events, end_minute):
    grouped = defaultdict(list)
    for event in sorted(events, key=lambda e: e['time_minute']):
        grouped[event['student_id']].append(event)
    rows = []
    for record in records:
        sessions = record['schedule']
        segments = [[] for _ in sessions]
        index = 0
        for event in grouped[record['student_id']]:
            if index >= len(sessions):
                break
            if event['event'] == 'finished':
                continue
            segments[index].append(event)
            if event['event'] in ('class_end', 'missed_class'):
                index += 1
        origin = record['initial_location']
        for session, segment in zip(sessions, segments):
            by_kind = {event['event']: event for event in segment}
            departure = by_kind.get('departure')
            arrival = by_kind.get('arrival')
            attendance = by_kind.get('class_start')
            missed = by_kind.get('missed_class')
            status = ('MISSED' if missed else 'COMPLETED' if 'class_end' in by_kind else
                      'IN CLASS' if attendance else 'WAITING' if arrival else
                      'WALKING' if departure else 'PENDING')
            late = attendance.get('lateness_minutes', 0) if attendance else None
            punctuality = ('MISSED' if missed else
                           f'LATE +{late:.2f} min' if late is not None and late > 1e-9 else
                           'ON TIME' if attendance or (arrival and arrival['time_minute'] <= session.start_minute + 1e-9) else
                           f"LATE +{arrival['time_minute'] - session.start_minute:.2f} min" if arrival else 'PENDING')
            travel = None
            if departure:
                stop = arrival or missed
                travel = max(0, (stop['time_minute'] if stop else end_minute) - departure['time_minute'])
            elif attendance:
                travel = 0.0
            rows.append(dict(student=record['student_id'], course=session.course or '-',
                             destination=session.destination, scheduled=session.start_minute,
                             departed=departure['time_minute'] if departure else None,
                             arrived=arrival['time_minute'] if arrival else None,
                             travel_minutes=travel, travel_partial=bool(departure and not arrival),
                             punctuality=punctuality, status=status))
    return rows


def print_journey_report(records, events, end_minute, clock):
    rows = journey_rows(records, events, end_minute)
    print('\nStudent travel and attendance (simulation time):')
    headers = ('Student', 'Course', 'To', 'Class at', 'Departed', 'Arrived', 'Walk min', 'Arrival status', 'Class status')
    cells = []
    for row in rows:
        time = lambda value: clock(value)[:-4] if value is not None else '-'
        travel = ('-' if row['travel_minutes'] is None else
                  f"{row['travel_minutes']:.2f}" + ('*' if row['travel_partial'] else ''))
        cells.append((row['student'], row['course'], row['destination'], time(row['scheduled']),
                      time(row['departed']), time(row['arrived']), travel, row['punctuality'], row['status']))
    widths = [max(len(str(row[i])) for row in [headers, *cells]) for i in range(len(headers))]
    def line(row):
        return ' | '.join(str(value).ljust(width) for value, width in zip(row, widths))
    print(line(headers))
    print('-+-'.join('-' * width for width in widths))
    for row in cells:
        print(line(row))
    if not rows:
        print('(No scheduled classes.)')
    if any(row['travel_partial'] for row in rows):
        print('* Walking time so far, or until the class was missed; journey not completed.')
    print('ON TIME includes early arrivals; no walking trip is shown as 0.00 when already at class.')
