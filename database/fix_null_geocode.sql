-- fix_null_geocode.sql
-- Backfill geocode_cache rows that failed to geocode, using coordinates
-- from the legacy points/locations.json. Idempotent: only touches rows that
-- are still NULL, so re-running won't clobber later manual fixes.

BEGIN;

UPDATE geocode_cache SET latitude = -34.9281805, longitude = 138.5999312, updated_at = now()
  WHERE location = 'Adelaide, SA, Australia' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 30.2711286, longitude = -97.7436995, updated_at = now()
  WHERE location = 'Austin, Texas, TX, USA' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 51.2254018, longitude = 6.7763137, updated_at = now()
  WHERE location = 'Boston Club, NRW, Germany' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 51.4538022, longitude = -2.5972985, updated_at = now()
  WHERE location = 'Bristol, Bristol, City of, United Kingdom' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 44.428448, longitude = 26.10404, updated_at = now()
  WHERE location = 'Bucharest, Romania, Bucharest, Romania' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 34.1816482, longitude = -118.3258554, updated_at = now()
  WHERE location = 'Burbank, California, California, USA' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 51.0460954, longitude = -114.065465, updated_at = now()
  WHERE location = 'Calgary, AB, Canada' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 35.2272086, longitude = -80.8430827, updated_at = now()
  WHERE location = 'Charlotte, NC, USA, North Carolina, USA' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 32.7762719, longitude = -96.7968559, updated_at = now()
  WHERE location = 'Dallas Ft. Worth, Texas, United States' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 39.7392364, longitude = -104.984862, updated_at = now()
  WHERE location = 'Denver, Colorado, Colorado, USA' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 55.9533456, longitude = -3.1883749, updated_at = now()
  WHERE location = 'Edinburgh, Scotland, Scotland, United Kingdom' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 57.7072326, longitude = 11.9670171, updated_at = now()
  WHERE location = 'Gothenburg, n/a, Sweden' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 34.851354, longitude = -82.3984882, updated_at = now()
  WHERE location = 'Greenville, South Carolina, SC, USA' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 62.9962879, longitude = 27.0132004, updated_at = now()
  WHERE location = 'Kuopio, Leppävirta, Finland' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 51.5073219, longitude = -0.1276474, updated_at = now()
  WHERE location = 'London, London, UK' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 51.5073219, longitude = -0.1276474, updated_at = now()
  WHERE location = 'London,  UK' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 51.5073219, longitude = -0.1276474, updated_at = now()
  WHERE location = 'London, UK' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 51.5073219, longitude = -0.1276474, updated_at = now()
  WHERE location = 'London, West Drayton, United Kingdom' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 45.7578137, longitude = 4.8320114, updated_at = now()
  WHERE location = 'LYON, rhones, FRANCE' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 53.4794892, longitude = -2.2451148, updated_at = now()
  WHERE location = 'Manchester, Manchester, UK' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 55.7505412, longitude = 37.6174782, updated_at = now()
  WHERE location = 'Moscow, Moscow region, Russia' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 49.163877, longitude = -123.938122, updated_at = now()
  WHERE location = 'Nanaimo, BC, Canada' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 41.8239891, longitude = -71.4128343, updated_at = now()
  WHERE location = 'Providence RI, RI, USA' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 35.7803977, longitude = -78.6390989, updated_at = now()
  WHERE location = 'Raleigh, NC, North Carolina, USA' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 53.198627, longitude = 50.113987, updated_at = now()
  WHERE location = 'Samara, Samara state, Russia' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 38.933099, longitude = -119.990193, updated_at = now()
  WHERE location = 'South Lake Tahoe (near Reno), NV, USA' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 59.3251172, longitude = 18.0710935, updated_at = now()
  WHERE location = 'Stockholm, Sweden, Sverige' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 43.6044622, longitude = 1.4442469, updated_at = now()
  WHERE location = 'Toulouse-Blagnac, Occitanie, France' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 36.1563122, longitude = -95.9927436, updated_at = now()
  WHERE location = 'Tulsa, OK, Ok, United States' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 63.8269763, longitude = 20.1595626, updated_at = now()
  WHERE location = 'Umeå, Nordmalings kommun, Sweden' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 38.8950368, longitude = -77.0365427, updated_at = now()
  WHERE location = 'Washington DC, MD, USA' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 38.8950368, longitude = -77.0365427, updated_at = now()
  WHERE location = 'Washington, DC, VA, USA' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 38.8950368, longitude = -77.0365427, updated_at = now()
  WHERE location = 'Washington, DC., VA, USA' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 39.7459468, longitude = -75.546589, updated_at = now()
  WHERE location = 'WILMINGTON DEL, Delaware, United States' AND (latitude IS NULL OR longitude IS NULL);
UPDATE geocode_cache SET latitude = 39.7459468, longitude = -75.546589, updated_at = now()
  WHERE location = 'WILMINGTON, DEL, Delaware, United States' AND (latitude IS NULL OR longitude IS NULL);

COMMIT;
