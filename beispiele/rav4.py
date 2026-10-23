# Toyota RAV4 (4. Generation, 2013–2015, AWD) mit Dachreling, Querträgern und Dachbox.
# Stilisiertes Modell in Originalgröße (mm); für 1:43 einfach SCALE = 1 / 43 setzen.
# Achsen: X = Fahrzeuglänge (Heck bei 0, Front bei +X), Y = Breite, Z = Höhe (Boden = 0).

SCALE = 1.0

LENGTH, WIDTH, HEIGHT = 4570, 1845, 1660
WHEELBASE, TRACK = 2660, 1570
REAR_AXLE = 980                        # Hecküberhang
FRONT_AXLE = REAR_AXLE + WHEELBASE
TIRE_R, TIRE_W, RIM_R = 362, 225, 215  # 225/65 R17
FLOOR = 230                            # Unterkante Karosserie
BELT = 1050                            # Fensterlinie
ROOF_HALF = 640                        # halbe Dachbreite
W2 = WIDTH / 2

# --- Karosserie: Schnitt aus Seiten-, Drauf- und Frontansicht -----------------
side_pts = [
    (40, FLOOR), (0, 520), (10, 1000), (70, 1230), (130, 1590), (260, 1650),
    (1000, HEIGHT), (2600, HEIGHT), (2950, 1610), (3560, 1070), (4180, 960),
    (4500, 850), (LENGTH, 640), (4545, 380), (4440, FLOOR),
]
plan_pts = [
    (0, -830), (150, -905), (600, -W2), (3900, -W2), (4400, -860), (LENGTH, -700),
    (LENGTH, 700), (4400, 860), (3900, W2), (600, W2), (150, 905), (0, 830),
]
front_pts = [
    (-W2, FLOOR), (W2, FLOOR), (W2, BELT - 150), (W2 - 40, BELT),
    (ROOF_HALF, HEIGHT), (-ROOF_HALF, HEIGHT), (-W2 + 40, BELT), (-W2, BELT - 150),
]

side_face = Plane.XZ * Polygon(*side_pts, align=None)
plan_face = Polygon(*plan_pts, align=None)
front_face = Plane.YZ * Polygon(*front_pts, align=None)

body = (
    extrude(side_face, amount=W2 + 100, both=True)
    & extrude(plan_face, amount=HEIGHT + 100)
    & Pos(-100, 0, 0) * extrude(front_face, amount=LENGTH + 200)
)

# Radläufe
for x in (REAR_AXLE, FRONT_AXLE):
    for s in (-1, 1):
        body -= Pos(x, s * (W2 - 140), TIRE_R + 10) * Rot(90, 0, 0) * Cylinder(TIRE_R + 45, 330)

# --- Fenster als 12 mm tiefe Vertiefungen -------------------------------------
DEPTH = 12
outside_side = extrude(side_face, amount=W2 + 100, both=True) - extrude(
    offset(side_face, amount=-DEPTH), amount=W2 + 100, both=True)
outside_front = Pos(-100, 0, 0) * (
    extrude(front_face, amount=LENGTH + 200) - extrude(offset(front_face, amount=-DEPTH), amount=LENGTH + 200))

# Seitenfenster (vorne, hinten, Dreieck hinten) – Umriss in der Seitenansicht
side_windows = [
    [(2620, BELT + 30), (3420, BELT + 30), (2920, 1590), (2620, 1600)],
    [(1500, BELT + 30), (2560, BELT + 30), (2560, 1600), (1450, 1610)],
    [(820, BELT + 60), (1440, BELT + 30), (1390, 1600), (1000, 1600)],
]
for pts in side_windows:
    body -= extrude(Plane.XZ * Polygon(*pts, align=None), amount=W2 + 100, both=True) & outside_front

# Windschutzscheibe und Heckscheibe – Bereiche in der Draufsicht
body -= Pos(3250, 0, 1340) * Box(700, 2 * (ROOF_HALF - 60), 560) & outside_side
body -= Pos(90, 0, 1390) * Box(200, 1100, 360) & outside_side

# Scheinwerfer, Kühlergrill, Rückleuchten
for s in (-1, 1):
    body -= Pos(4470, s * 650, 820) * Box(260, 420, 110) & outside_side
    body -= Pos(40, s * 770, 1050) * Box(160, 260, 140) & outside_side
body -= Pos(4560, 0, 500) * Box(60, 900, 180) & outside_side
body -= Pos(4520, 0, 760) * Box(160, 520, 70) & outside_side
body -= Pos(5, 0, 930) * Box(30, 320, 130)                      # Kennzeichenmulde

parts = [body]

# --- Räder: Reifen, Felge mit fünf Speichen ------------------------------------
for x in (REAR_AXLE, FRONT_AXLE):
    for s in (-1, 1):
        y = s * TRACK / 2
        tire = Pos(x, y, TIRE_R) * Rot(90, 0, 0) * Cylinder(TIRE_R, TIRE_W)
        tire -= Pos(x, y + s * TIRE_W / 2, TIRE_R) * Rot(90, 0, 0) * Cylinder(RIM_R, 60)
        rim = Pos(x, y + s * (TIRE_W / 2 - 25), TIRE_R) * Rot(90, 0, 0) * Cylinder(60, 40)
        for k in range(5):
            rim += (Pos(x, y + s * (TIRE_W / 2 - 25), TIRE_R) * Rot(0, 72 * k, 0)
                    * Pos(0, 0, RIM_R / 2) * Box(55, 30, RIM_R))
        rim += Pos(x, y + s * (TIRE_W / 2 - 45), TIRE_R) * Rot(90, 0, 0) * (
            Cylinder(RIM_R, 12) - Cylinder(RIM_R - 25, 14))
        parts += [tire, rim]

# --- Anbauteile ---------------------------------------------------------------
for s in (-1, 1):
    # Trittbretter zwischen den Rädern
    parts.append(Pos((REAR_AXLE + FRONT_AXLE) / 2, s * (W2 - 10), 300) * Box(1700, 110, 35))
    # Außenspiegel
    parts.append(Pos(3400, s * (W2 + 30), 1130) * Box(170, 140, 110))
    # Dachreling
    parts.append(Pos(1600, s * (ROOF_HALF - 80), HEIGHT + 25) * Box(2200, 40, 50))
    # Querträger-Füße
    for x in (1000, 2200):
        parts.append(Pos(x, s * (ROOF_HALF - 80), HEIGHT + 70) * Box(90, 70, 40))

# Querträger
for x in (1000, 2200):
    parts.append(Pos(x, 0, HEIGHT + 105) * Box(80, 2 * ROOF_HALF + 60, 30))

# Dachbox (flach, abgerundet)
roof_box = Pos(1550, 0, HEIGHT + 210) * Box(2000, 800, 180)
roof_box = fillet(roof_box.edges().filter_by(Axis.Y), radius=85)
roof_box = fillet(roof_box.edges().filter_by(Axis.X), radius=40)
parts.append(roof_box)

result = scale(Compound(parts), SCALE)
