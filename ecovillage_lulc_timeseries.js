// ============================================================================
// Ecovillage LULC Timeseries Mapping with Sentinel-2 (10m) & Landsat (30m)
// Years: 2015-2024 | Buffer: User-selectable via UI | Resolution: Upscaled to 1m for viz
// Classes (ESRI harmonized): 0=water, 1=trees, 2=flooded_veg, 3=crops, 4=built, 
// 5=scrub_shrub, 6=bare, 7=snow_ice, 8=grass_rangeland (2024: NDVI proxy, 0-5)
// ============================================================================

print('Starting Ecovillage LULC Timeseries Script...');

// Define ecovillages with deduplication
var ecovillagesRaw = [
  {name: 'Findhorn Ecovillage', country: 'Scotland', lat: 57.6450, lon: -3.5600},
  {name: 'Crystal Waters Ecovillage', country: 'Australia', lat: -27.1389, lon: 152.8333},
  {name: 'Auroville', country: 'India', lat: 12.0220, lon: 79.7936},
  {name: 'Damanhur Federation', country: 'Italy', lat: 45.3833, lon: 8.0167},
  {name: 'The Farm', country: 'USA (Tennessee)', lat: 35.4639, lon: -86.4286},
  {name: 'Sieben Linden Ecovillage', country: 'Germany', lat: 53.0550, lon: 9.0750},
  {name: 'Tamera Healing Biotope', country: 'Portugal', lat: 37.9778, lon: -8.7628},
  {name: 'Ithaca Ecovillage', country: 'USA (New York)', lat: 42.4266, lon: -76.5135},
  {name: 'Gaia Ashram', country: 'Thailand', lat: 13.8518, lon: 100.4743},
  {name: 'Valldaura Labs', country: 'Spain', lat: 41.4181, lon: 1.9819},
  {name: 'Torri Superiore', country: 'Italy', lat: 43.9175, lon: 7.7267},
  {name: 'Cloughjordan Ecovillage', country: 'Ireland', lat: 53.0550, lon: -7.9667},
  {name: 'Dancing Rabbit Ecovillage', country: 'USA (Missouri)', lat: 40.2806, lon: -91.0667},
  {name: 'Earthaven Ecovillage', country: 'USA (North Carolina)', lat: 35.2200, lon: -82.6100},
  {name: 'Los Angeles Eco-Village', country: 'USA (California)', lat: 34.0195, lon: -118.2642},
  {name: 'La Cité Écologique', country: 'Canada', lat: 45.5017, lon: -72.5969},
  {name: 'Huehuecoyotl Ecovillage', country: 'Mexico', lat: 19.8863, lon: -96.7297},
  {name: 'Lammas Ecovillage', country: 'Wales', lat: 51.9433, lon: -3.6567},
  {name: 'Eco Truly Park', country: 'Peru', lat: -12.0464, lon: -76.9750},
  {name: 'ZEGG Ecovillage', country: 'Germany', lat: 52.3667, lon: 13.6833},
  {name: 'Keveral Farm', country: 'UK', lat: 50.4681, lon: -4.9328},
  {name: 'Narara Ecovillage', country: 'Australia', lat: -33.3169, lon: 151.3981},
  {name: 'Sunseed Desert Technology', country: 'Spain', lat: 36.7486, lon: -2.3722},
  {name: 'Sirius Community', country: 'USA (Massachusetts)', lat: 42.3601, lon: -71.0589},
  {name: 'Solheimar Ecovillage', country: 'Iceland', lat: 63.8333, lon: -19.8333},
  {name: 'Longo Maï', country: 'France', lat: 45.3500, lon: 6.7167},
  {name: 'Ecodorp Boekel', country: 'Netherlands', lat: 51.5833, lon: 5.5500},
  {name: 'Enright Ridge Urban Ecovillage', country: 'USA (Ohio)', lat: 41.4925, lon: -81.6833},
  {name: 'Kibbutz Lotan', country: 'Israel', lat: 30.8047, lon: 34.8378},
  {name: 'Ecovillage of Sekem', country: 'Egypt', lat: 30.5111, lon: 31.3500},
  {name: 'Port Townsend EcoVillage', country: 'USA (Washington)', lat: 48.1181, lon: -122.7610},
  {name: 'Finca Tierra', country: 'Costa Rica', lat: 10.0000, lon: -84.2361},
  {name: 'EcoYoff', country: 'Senegal', lat: 14.6928, lon: -17.5243},
  {name: 'EcoDal', country: 'Denmark', lat: 56.2639, lon: 9.5018},
  {name: 'Rancho Margot', country: 'Costa Rica', lat: 9.7489, lon: -83.7384},
  {name: 'Quinta do Vale da Lama', country: 'Portugal', lat: 39.2750, lon: -8.4389},
  {name: 'Eco Caminhos', country: 'Brazil', lat: -22.7538, lon: -46.6956},
  {name: 'Aldeafeliz Ecovillage', country: 'Colombia', lat: 4.7110, lon: -74.0721},
  {name: 'Green School Community', country: 'Bali, Indonesia', lat: -8.6500, lon: 115.3667},
  {name: 'Arterra Bizimodu', country: 'Spain', lat: 42.6952, lon: -2.8449},
  {name: 'Sunriver Ecovillage', country: 'USA (Oregon)', lat: 43.7003, lon: -121.5050},
  {name: 'Lakabe', country: 'Spain', lat: 42.7833, lon: -1.6667},
  {name: 'Ecovillage Pödelwitz', country: 'Germany', lat: 51.6667, lon: 12.8333},
  {name: 'Ecovillage Kurjen Tila', country: 'Finland', lat: 62.8833, lon: 24.9667},
  {name: 'Peliti Land', country: 'Greece', lat: 39.0742, lon: 21.8243},
  {name: 'Christiania', country: 'Denmark', lat: 55.6756, lon: 12.5939},
  {name: 'Bab Zouina', country: 'Morocco', lat: 31.6295, lon: -5.1721},
  {name: 'Hurdal Ecovillage', country: 'Norway', lat: 60.0833, lon: 11.5333},
  {name: 'Eco Truly Ecovillage', country: 'Ecuador', lat: -0.9186, lon: -78.1835},
  {name: 'Tinkers Bubble', country: 'UK', lat: 51.5074, lon: -2.1398},
  {name: 'Green Village Ubud', country: 'Indonesia', lat: -8.5069, lon: 115.2625},
  {name: 'Mount Shasta Ecovillage', country: 'USA', lat: 41.3090, lon: -122.3050},
  {name: 'Blue Clay Farm', country: 'USA', lat: 40.4416, lon: -74.0070},
  {name: 'Gaviotas', country: 'Colombia', lat: 5.2128, lon: -72.9150},
  {name: 'Finca Morpho', country: 'Costa Rica', lat: 9.1450, lon: -79.5200},
  {name: 'Gaia Education Campus', country: 'Scotland', lat: 57.1000, lon: -4.4500},
  {name: 'Cae Mabon', country: 'Wales', lat: 51.9500, lon: -3.9667},
  {name: 'Camphill Communities', country: 'Europe', lat: 52.3667, lon: 13.6833},
  {name: 'Permatierra', country: 'Chile', lat: -37.4701, lon: -72.3355},
  {name: 'Canelones Ecovillage', country: 'Uruguay', lat: -34.6037, lon: -56.2019},
  {name: 'Hummingbird Community', country: 'USA (New Mexico)', lat: 35.0844, lon: -106.6504},
  {name: 'Highgrove Ecovillage', country: 'Canada', lat: 49.2827, lon: -123.1207},
  {name: 'Saladero Ecolodge', country: 'Costa Rica', lat: 9.6386, lon: -85.9043},
  {name: 'Karuna Center', country: 'Nepal', lat: 27.7172, lon: 85.3240},
  {name: 'Valle de Sensaciones', country: 'Spain', lat: 38.2975, lon: -0.6882},
  {name: 'Eco Caminhos II', country: 'Brazil', lat: -23.5505, lon: -46.6333},
  {name: 'Aldeia de São José', country: 'Portugal', lat: 37.4000, lon: -8.0833},
  {name: 'Findhorn Park Ecohomes', country: 'Scotland', lat: 57.6450, lon: -3.5600},
  {name: 'Solarsiedlung Freiburg', country: 'Germany', lat: 47.9990, lon: 7.8621},
  {name: 'The Vale', country: 'UK', lat: 51.5074, lon: -0.1278},
  {name: 'Bruderhof Communities', country: 'USA', lat: 42.6526, lon: -73.7562},
  {name: 'Aurora Ecovillage', country: 'Argentina', lat: -34.6037, lon: -58.3816},
  {name: 'Moksha EcoVillage', country: 'Sri Lanka', lat: 6.9271, lon: 80.7789},
  {name: 'Panal Community', country: 'Chile', lat: -38.9516, lon: -71.5596},
  {name: 'Los Horcones', country: 'Mexico', lat: 26.0333, lon: -100.9833},
  {name: 'Ndem Village', country: 'Senegal', lat: 14.1598, lon: -14.1246},
  {name: 'Midsummer Common Ecovillage', country: 'UK', lat: 52.2015, lon: 0.1239},
  {name: 'Libera Terra', country: 'Italy', lat: 38.1100, lon: 14.5600},
  {name: 'Eco Truly India', country: 'India', lat: 13.0827, lon: 80.2707},
  {name: 'Moinhos Ecovillage', country: 'Brazil', lat: -27.5954, lon: -48.5480},
  {name: 'EcoTerra Community', country: 'New Zealand', lat: -41.2865, lon: 174.7762},
  {name: 'Ecolonia', country: 'Netherlands', lat: 52.1326, lon: 6.9241},
  {name: 'Masdar Living Community', country: 'UAE', lat: 24.1092, lon: 54.6139},
  {name: 'Kibbutz Ketura', country: 'Israel', lat: 29.7604, lon: 34.8378},
  {name: 'Edenhope Ecovillage', country: 'Australia', lat: -37.5105, lon: 141.3325},
  {name: 'Craggy Island Ecovillage', country: 'Ireland', lat: 53.1489, lon: -9.2805},
  {name: 'ReGen Villages', country: 'Netherlands', lat: 52.0704, lon: 4.3007},
  {name: 'EcoMondo', country: 'Spain', lat: 40.4168, lon: -3.7038},
  {name: 'Permaculture Institute', country: 'Jordan', lat: 31.9454, lon: 35.9284},
  {name: 'Rancho San Ricardo', country: 'Mexico', lat: 19.4326, lon: -99.1332},
  {name: 'EcoMoor', country: 'Germany', lat: 53.6333, lon: 8.2167},
  {name: 'Hockerton Housing Project', country: 'UK', lat: 53.2833, lon: -0.9833},
  {name: 'BedZED', country: 'UK', lat: 51.3990, lon: -0.1640},
  {name: 'Nordhavn', country: 'Denmark', lat: 55.6721, lon: 12.6097},
  {name: 'Vauban District', country: 'Germany', lat: 47.9990, lon: 7.8621},
  {name: 'EcoVillage Living Center', country: 'USA', lat: 42.4534, lon: -76.4735},
  {name: 'Shumei Natural Agriculture', country: 'Japan', lat: 35.0753, lon: 135.7674},
  {name: 'Greenworld Eco Community', country: 'Malaysia', lat: 3.1390, lon: 101.6869}
];

// Deduplicate using ee.List
var uniqueCoords = ee.List([]);
var ecovillages = ee.FeatureCollection(ecovillagesRaw.map(function(props, index) {
  var coordKey = ee.String(props.lat).cat(',').cat(ee.String(props.lon));
  var isDuplicate = uniqueCoords.contains(coordKey);
  var newProps = ee.Algorithms.If(
    isDuplicate,
    ee.Dictionary(props).set('name', ee.String(props.name).cat('_2')),
    props
  );
  uniqueCoords = uniqueCoords.add(coordKey);
  return ee.Feature(ee.Geometry.Point([props.lon, props.lat]), newProps);
}));
print('Ecovillages loaded:', ecovillages.size());  // Should be 100

// User parameters
var START_YEAR = 2015;
var END_YEAR = 2024;  // 2024 uses NDVI proxy
var DEFAULT_BUFFER = 2000;  // Increased for sampling
var CLASS_NAMES = ['water', 'trees', 'flooded_veg', 'crops', 'built', 'scrub_shrub', 'bare', 'snow_ice', 'grass_rangeland'];
var PALETTE = ['blue', 'darkgreen', 'lightgreen', 'yellow', 'gray', 'orange', 'brown', 'white', 'limegreen'];

// Visualization params for LULC
var visParams = {
  min: 0,
  max: 8,
  palette: PALETTE
};

// UI for buffer selection
var bufferSlider = ui.Slider({
  min: 0,
  max: 5000,
  value: DEFAULT_BUFFER,
  step: 100,
  style: {width: '300px'}
});
var bufferLabel = ui.Label('Select Buffer Distance (meters):');
var refreshButton = ui.Button('Refresh Map', function() {
  updateMap(bufferSlider.getValue());
});
var bufferPanel = ui.Panel([bufferLabel, bufferSlider, refreshButton]);
ui.root.add(bufferPanel);

// Function to update study area
function updateStudyArea(bufferDistance) {
  var buffers = ecovillages.map(function(f) {
    return f.buffer(ee.Number(bufferDistance).max(0));
  });
  return ee.Geometry.MultiPolygon(buffers.geometry().geometries());
}

// Initial study area
var studyArea = updateStudyArea(DEFAULT_BUFFER);
print('Initial study area created with buffer:', DEFAULT_BUFFER, 'meters');

// Center map on first ecovillage
Map.centerObject(ecovillages.first(), 12);

// Function for ESRI LULC (2017-2023)
function getEsriLulc(year) {
  var start = ee.Date.fromYMD(year, 1, 1);
  var end = start.advance(1, 'year');
  var image = ee.ImageCollection('projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m_TS')
    .filterDate(start, end)
    .first()
    .select('b1')
    .clip(studyArea)
    .resample('bilinear')
    .reproject({crs: 'EPSG:4326', scale: 1});
  return image.set('year', year, 'system:time_start', start.millis());
}

// Function for Landsat LULC (2015-2016)
function getLandsatLulc(year) {
  var start = ee.Date.fromYMD(year, 1, 1);
  var end = start.advance(1, 'year');
  var landsat = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
    .filterBounds(studyArea)
    .filterDate(start, end)
    .filter(ee.Filter.lt('CLOUD_COVER', 20))
    .median()
    .clip(studyArea)
    .select(['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7'],
            ['B2', 'B3', 'B4', 'B5', 'B6', 'B7'])
    .multiply(0.0000275).add(-0.2)
    .addBands(ee.Image('USGS/SRTMGL1_003').clip(studyArea).select('elevation'));

  var esri2017 = ee.ImageCollection('projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m_TS')
    .filterDate('2017-01-01', '2018-01-01').first();
  var trainingFc = esri2017.sample({
    region: studyArea,
    scale: 30,
    numPixels: 5000
  });
  print('Training samples for year', year, ':', trainingFc.size());
  var trainingCount = trainingFc.size();
  var training = ee.Algorithms.If(
    trainingCount.gt(0),
    landsat.sampleRegions({
      collection: trainingFc.limit(9000),
      properties: ['b1'],
      scale: 30
    }),
    // Fallback: Global sampling
    landsat.sampleRegions({
      collection: esri2017.sample({
        region: ee.Geometry.BBox(-180, -60, 180, 60),
        scale: 30,
        numPixels: 5000
      }).limit(9000),
      properties: ['b1'],
      scale: 30
    })
  );

  var classifier = ee.Classifier.smileRandomForest(50).train({
    features: training,
    classProperty: 'b1',
    inputProperties: landsat.bandNames()
  });

  var classified = landsat.classify(classifier).rename('classification');
  return classified
    .resample('bilinear')
    .reproject({crs: 'EPSG:4326', scale: 1})
    .set('year', year, 'system:time_start', start.millis());
}

// Function for 2024 proxy (Sentinel-2 NDVI, scaled 0-5)
function getProxyLulc(year) {
  var start = ee.Date.fromYMD(year, 1, 1);
  var end = start.advance(1, 'year');
  var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(studyArea)
    .filterDate(start, end)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
    .median()
    .clip(studyArea)
    .normalizedDifference(['B8', 'B4']).rename('ndvi')
    .multiply(4).add(1).int8().clamp(0, 5)
    .resample('bilinear')
    .reproject({crs: 'EPSG:4326', scale: 1});
  return s2.set('year', year, 'system:time_start', start.millis());
}

// Generate timeseries collection
var years = ee.List.sequence(START_YEAR, END_YEAR);
var lutCollection = ee.ImageCollection.fromImages(
  years.map(function(year) {
    var y = ee.Number(year);
    return ee.Algorithms.If(
      y.lte(2016), getLandsatLulc(y),
      ee.Algorithms.If(
        y.lte(2023), getEsriLulc(y),
        getProxyLulc(y)
      )
    );
  })
);
print('LULC Timeseries Collection created:', lutCollection);

// Function to update map layers
function updateMap(bufferDist) {
  Map.layers().reset();
  studyArea = updateStudyArea(bufferDist);
  print('Updated study area with buffer:', bufferDist, 'meters');

  // Rebuild collection
  lutCollection = ee.ImageCollection.fromImages(
    years.map(function(year) {
      var y = ee.Number(year);
      return ee.Algorithms.If(
        y.lte(2016), getLandsatLulc(y),
        ee.Algorithms.If(
          y.lte(2023), getEsriLulc(y),
          getProxyLulc(y)
        )
      );
    })
  );

  // Add layers server-side
  lutCollection.map(function(img) {
    var year = ee.Image(img).get('year');
    var showLayer = ee.Number(year).gte(2020);
    Map.addLayer(
      img,
      visParams,
      ee.String('LULC ').cat(ee.String(ee.Number(year).format('%d'))),
      showLayer
    );
  });

  // Tree loss proxy
  var base2017 = lutCollection.filter(ee.Filter.eq('year', 2017)).first();
  var change2024 = lutCollection.filter(ee.Filter.eq('year', 2024)).first();
  var treeLoss = ee.Algorithms.If(
    base2017.and(change2024),
    base2017.eq(1).and(change2024.lt(0.3)).selfMask(),
    ee.Image().paint(studyArea, 0)
  );
  Map.addLayer(treeLoss, {palette: ['red']}, 'Tree Loss Proxy 2017-2024', true);
  print('Map updated with layers and tree loss proxy');
}

// Initial map update
updateMap(DEFAULT_BUFFER);

// Compute and print stats
var stats = lutCollection.map(function(img) {
  var year = ee.Image(img).get('year');
  var pixelArea = ee.Image.pixelArea();
  var areas = ee.Algorithms.If(
    img,
    img.addBands(pixelArea).reduceRegion({
      reducer: ee.Reducer.sum().group({
        groupField: 1,
        groupName: 'class'
      }),
      geometry: studyArea,
      scale: 10,
      maxPixels: 1e9
    }),
    {}
  );
  return ee.Feature(null, {year: year}).set(areas);
});
print('Annual LULC Stats (sq m per class):', stats);

// Exports (uncomment to run)
Export.table.toDrive({
  collection: stats,
  description: 'Ecovillage_LULC_Stats_2015_2024',
  fileFormat: 'CSV'
});

var latestLulc = lutCollection.filter(ee.Filter.eq('year', 2024)).first();
Export.image.toDrive({
  image: latestLulc.visualize(visParams),
  description: 'Ecovillage_LULC_2024_1mViz',
  scale: 1,
  region: studyArea,
  maxPixels: 1e9
});

print('Script completed. Use slider and Refresh Map button to adjust buffer.');

// ============================================================================
// END SCRIPT
// Run in GEE Code Editor: https://code.earthengine.google.com/
// For single site: ecovillages = ecovillages.filter(ee.Filter.eq('name', 'Auroville'));
// ============================================================================