<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis autoRefreshMode="Disabled" autoRefreshTime="0" hasScaleBasedVisibilityFlag="0" labelsEnabled="1" layerType="Vector" maxScale="0" minScale="0" simplifyAlgorithm="0" simplifyDrawingHints="1" simplifyDrawingTol="1" simplifyLocal="1" simplifyMaxScale="1" styleCategories="Symbology|Labeling|Rendering" symbologyReferenceScale="-1" version="4.2.2-Belém do Pará">
 <renderer-v2 enableorderby="0" forceraster="0" referencescale="-1" symbollevels="0" type="RuleRenderer">
  <rules key="{6ccef44e-3701-4dc4-9284-aefda423b785}">
   <rule filter="right(&quot;vt_alti&quot;,1)='5'" key="{01daa1fc-69e0-4edf-a117-8c86aadc558c}" label="5m" scalemaxdenom="15000" scalemindenom="1" symbol="0"/>
   <rule filter="right(&quot;vt_alti&quot;,2)='10'or right(&quot;vt_alti&quot;,2)='30'or right(&quot;vt_alti&quot;,2)='50'or right(&quot;vt_alti&quot;,2)='70'or right(&quot;vt_alti&quot;,2)='90' " key="{fa345bea-d56f-41ff-b63b-1150e898e380}" label="10m" scalemaxdenom="70000" scalemindenom="1" symbol="1"/>
   <rule filter="right(&quot;vt_alti&quot;,2)='20'or right(&quot;vt_alti&quot;,2)='40'or right(&quot;vt_alti&quot;,2)='60'or right(&quot;vt_alti&quot;,2)='80'" key="{d5b60594-caad-410d-bfa1-52f829d2d0f9}" label="20m" scalemaxdenom="40001" scalemindenom="1" symbol="2"/>
   <rule filter="right(&quot;vt_alti&quot;,2)='00'" key="{6a1133ac-afd1-4666-8b8e-707aff8889c2}" label="100m" scalemaxdenom="50001" scalemindenom="1" symbol="3"/>
  </rules>
  <symbols>
   <symbol alpha="1" clip_to_extent="1" force_rhr="0" frame_rate="10" is_animated="0" name="0" type="line">
    <data_defined_properties>
     <Option type="Map">
      <Option name="name" type="QString" value=""/>
      <Option name="properties"/>
      <Option name="type" type="QString" value="collection"/>
     </Option>
    </data_defined_properties>
    <layer class="SimpleLine" enabled="1" id="{7a32ceba-a157-42c2-a43b-089f5e74a788}" locked="0" pass="0">
     <Option type="Map">
      <Option name="align_dash_pattern" type="QString" value="0"/>
      <Option name="capstyle" type="QString" value="square"/>
      <Option name="customdash" type="QString" value="5;2"/>
      <Option name="customdash_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="customdash_unit" type="QString" value="MM"/>
      <Option name="dash_pattern_offset" type="QString" value="0"/>
      <Option name="dash_pattern_offset_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="dash_pattern_offset_unit" type="QString" value="MM"/>
      <Option name="draw_inside_polygon" type="QString" value="0"/>
      <Option name="joinstyle" type="QString" value="bevel"/>
      <Option name="line_color" type="QString" value="58,28,0,255,rgb:0.227451,0.1098039,0,1"/>
      <Option name="line_style" type="QString" value="solid"/>
      <Option name="line_width" type="QString" value="0.03"/>
      <Option name="line_width_unit" type="QString" value="MM"/>
      <Option name="offset" type="QString" value="0"/>
      <Option name="offset_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="offset_unit" type="QString" value="MM"/>
      <Option name="ring_filter" type="QString" value="0"/>
      <Option name="trim_distance_end" type="QString" value="0"/>
      <Option name="trim_distance_end_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="trim_distance_end_unit" type="QString" value="MM"/>
      <Option name="trim_distance_start" type="QString" value="0"/>
      <Option name="trim_distance_start_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="trim_distance_start_unit" type="QString" value="MM"/>
      <Option name="tweak_dash_pattern_on_corners" type="QString" value="0"/>
      <Option name="use_custom_dash" type="QString" value="0"/>
      <Option name="width_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
     </Option>
     <data_defined_properties>
      <Option type="Map">
       <Option name="name" type="QString" value=""/>
       <Option name="properties"/>
       <Option name="type" type="QString" value="collection"/>
      </Option>
     </data_defined_properties>
    </layer>
   </symbol>
   <symbol alpha="1" clip_to_extent="1" force_rhr="0" frame_rate="10" is_animated="0" name="1" type="line">
    <data_defined_properties>
     <Option type="Map">
      <Option name="name" type="QString" value=""/>
      <Option name="properties"/>
      <Option name="type" type="QString" value="collection"/>
     </Option>
    </data_defined_properties>
    <layer class="SimpleLine" enabled="1" id="{c7a1e2dd-dfdf-4602-913c-ec12ffb5b3a8}" locked="0" pass="0">
     <Option type="Map">
      <Option name="align_dash_pattern" type="QString" value="0"/>
      <Option name="capstyle" type="QString" value="square"/>
      <Option name="customdash" type="QString" value="5;2"/>
      <Option name="customdash_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="customdash_unit" type="QString" value="MM"/>
      <Option name="dash_pattern_offset" type="QString" value="0"/>
      <Option name="dash_pattern_offset_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="dash_pattern_offset_unit" type="QString" value="MM"/>
      <Option name="draw_inside_polygon" type="QString" value="0"/>
      <Option name="joinstyle" type="QString" value="bevel"/>
      <Option name="line_color" type="QString" value="58,28,0,255,rgb:0.227451,0.1098039,0,1"/>
      <Option name="line_style" type="QString" value="solid"/>
      <Option name="line_width" type="QString" value="0.03"/>
      <Option name="line_width_unit" type="QString" value="MM"/>
      <Option name="offset" type="QString" value="0"/>
      <Option name="offset_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="offset_unit" type="QString" value="MM"/>
      <Option name="ring_filter" type="QString" value="0"/>
      <Option name="trim_distance_end" type="QString" value="0"/>
      <Option name="trim_distance_end_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="trim_distance_end_unit" type="QString" value="MM"/>
      <Option name="trim_distance_start" type="QString" value="0"/>
      <Option name="trim_distance_start_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="trim_distance_start_unit" type="QString" value="MM"/>
      <Option name="tweak_dash_pattern_on_corners" type="QString" value="0"/>
      <Option name="use_custom_dash" type="QString" value="0"/>
      <Option name="width_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
     </Option>
     <data_defined_properties>
      <Option type="Map">
       <Option name="name" type="QString" value=""/>
       <Option name="properties"/>
       <Option name="type" type="QString" value="collection"/>
      </Option>
     </data_defined_properties>
    </layer>
   </symbol>
   <symbol alpha="1" clip_to_extent="1" force_rhr="0" frame_rate="10" is_animated="0" name="2" type="line">
    <data_defined_properties>
     <Option type="Map">
      <Option name="name" type="QString" value=""/>
      <Option name="properties"/>
      <Option name="type" type="QString" value="collection"/>
     </Option>
    </data_defined_properties>
    <layer class="SimpleLine" enabled="1" id="{da58793a-929e-439d-8c95-5a04814359eb}" locked="0" pass="0">
     <Option type="Map">
      <Option name="align_dash_pattern" type="QString" value="0"/>
      <Option name="capstyle" type="QString" value="square"/>
      <Option name="customdash" type="QString" value="5;2"/>
      <Option name="customdash_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="customdash_unit" type="QString" value="MM"/>
      <Option name="dash_pattern_offset" type="QString" value="0"/>
      <Option name="dash_pattern_offset_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="dash_pattern_offset_unit" type="QString" value="MM"/>
      <Option name="draw_inside_polygon" type="QString" value="0"/>
      <Option name="joinstyle" type="QString" value="bevel"/>
      <Option name="line_color" type="QString" value="58,28,0,255,rgb:0.227451,0.1098039,0,1"/>
      <Option name="line_style" type="QString" value="solid"/>
      <Option name="line_width" type="QString" value="0.1"/>
      <Option name="line_width_unit" type="QString" value="MM"/>
      <Option name="offset" type="QString" value="0"/>
      <Option name="offset_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="offset_unit" type="QString" value="MM"/>
      <Option name="ring_filter" type="QString" value="0"/>
      <Option name="trim_distance_end" type="QString" value="0"/>
      <Option name="trim_distance_end_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="trim_distance_end_unit" type="QString" value="MM"/>
      <Option name="trim_distance_start" type="QString" value="0"/>
      <Option name="trim_distance_start_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="trim_distance_start_unit" type="QString" value="MM"/>
      <Option name="tweak_dash_pattern_on_corners" type="QString" value="0"/>
      <Option name="use_custom_dash" type="QString" value="0"/>
      <Option name="width_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
     </Option>
     <data_defined_properties>
      <Option type="Map">
       <Option name="name" type="QString" value=""/>
       <Option name="properties"/>
       <Option name="type" type="QString" value="collection"/>
      </Option>
     </data_defined_properties>
    </layer>
   </symbol>
   <symbol alpha="1" clip_to_extent="1" force_rhr="0" frame_rate="10" is_animated="0" name="3" type="line">
    <data_defined_properties>
     <Option type="Map">
      <Option name="name" type="QString" value=""/>
      <Option name="properties"/>
      <Option name="type" type="QString" value="collection"/>
     </Option>
    </data_defined_properties>
    <layer class="SimpleLine" enabled="1" id="{0a1e3288-c9b5-4d69-b0b4-4cf7dfa6f87e}" locked="0" pass="0">
     <Option type="Map">
      <Option name="align_dash_pattern" type="QString" value="0"/>
      <Option name="capstyle" type="QString" value="square"/>
      <Option name="customdash" type="QString" value="5;2"/>
      <Option name="customdash_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="customdash_unit" type="QString" value="MM"/>
      <Option name="dash_pattern_offset" type="QString" value="0"/>
      <Option name="dash_pattern_offset_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="dash_pattern_offset_unit" type="QString" value="MM"/>
      <Option name="draw_inside_polygon" type="QString" value="0"/>
      <Option name="joinstyle" type="QString" value="bevel"/>
      <Option name="line_color" type="QString" value="58,28,0,255,rgb:0.227451,0.1098039,0,1"/>
      <Option name="line_style" type="QString" value="solid"/>
      <Option name="line_width" type="QString" value="0.23"/>
      <Option name="line_width_unit" type="QString" value="MM"/>
      <Option name="offset" type="QString" value="0"/>
      <Option name="offset_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="offset_unit" type="QString" value="MM"/>
      <Option name="ring_filter" type="QString" value="0"/>
      <Option name="trim_distance_end" type="QString" value="0"/>
      <Option name="trim_distance_end_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="trim_distance_end_unit" type="QString" value="MM"/>
      <Option name="trim_distance_start" type="QString" value="0"/>
      <Option name="trim_distance_start_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
      <Option name="trim_distance_start_unit" type="QString" value="MM"/>
      <Option name="tweak_dash_pattern_on_corners" type="QString" value="0"/>
      <Option name="use_custom_dash" type="QString" value="0"/>
      <Option name="width_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
     </Option>
     <data_defined_properties>
      <Option type="Map">
       <Option name="name" type="QString" value=""/>
       <Option name="properties"/>
       <Option name="type" type="QString" value="collection"/>
      </Option>
     </data_defined_properties>
    </layer>
   </symbol>
  </symbols>
  <data-defined-properties>
   <Option type="Map">
    <Option name="name" type="QString" value=""/>
    <Option name="properties"/>
    <Option name="type" type="QString" value="collection"/>
   </Option>
  </data-defined-properties>
 </renderer-v2>
 <selection mode="Default">
  <selectionColor invalid="1"/>
 </selection>
 <labeling type="rule-based">
  <rules key="{4e700764-ade1-4af5-aa99-a2562c2ea3e7}">
   <rule active="0" key="{542975d2-20f4-4c01-abcf-143b8f070f76}">
    <settings calloutType="simple">
     <text-style allowHtml="0" blendMode="0" capitalization="0" fieldName="vt_alti" fontFamily="MS UI Gothic" fontItalic="0" fontKerning="1" fontLetterSpacing="0" fontSize="4" fontSizeMapUnitScale="3x:0,0,0,0,0,0" fontSizeUnit="Point" fontStrikeout="0" fontUnderline="0" fontWeight="400" fontWordSpacing="0" forcedBold="0" forcedItalic="0" isExpression="0" legendString="Aa" multilineHeight="1" multilineHeightUnit="Percentage" namedStyle="Normal" previewBkgrdColor="0,0,0,255,rgb:0,0,0,1" tabStopDistance="80" tabStopDistanceMapUnitScale="3x:0,0,0,0,0,0" tabStopDistanceUnit="Point" textColor="93,53,15,255,rgb:0.3647059,0.2078431,0.0588235,1" textOpacity="1" textOrientation="horizontal" useSubstitutions="0">
      <families/>
      <text-buffer bufferBlendMode="0" bufferColor="255,255,255,255,rgb:1,1,1,1" bufferDraw="1" bufferJoinStyle="128" bufferNoFill="1" bufferOpacity="1" bufferSize="1" bufferSizeMapUnitScale="3x:0,0,0,0,0,0" bufferSizeUnits="MM"/>
      <text-mask maskEnabled="0" maskJoinStyle="128" maskOpacity="1" maskSize="1.5" maskSize2="1.5" maskSizeMapUnitScale="3x:0,0,0,0,0,0" maskSizeUnits="MM" maskType="0" maskedSymbolLayers=""/>
      <background shapeBlendMode="0" shapeBorderColor="128,128,128,255,rgb:0.5019608,0.5019608,0.5019608,1" shapeBorderWidth="0" shapeBorderWidthMapUnitScale="3x:0,0,0,0,0,0" shapeBorderWidthUnit="MM" shapeDraw="0" shapeFillColor="255,255,255,255,rgb:1,1,1,1" shapeJoinStyle="64" shapeOffsetMapUnitScale="3x:0,0,0,0,0,0" shapeOffsetUnit="MM" shapeOffsetX="0" shapeOffsetY="0" shapeOpacity="1" shapeRadiiMapUnitScale="3x:0,0,0,0,0,0" shapeRadiiUnit="MM" shapeRadiiX="0" shapeRadiiY="0" shapeRotation="0" shapeRotationType="0" shapeSVGFile="" shapeSizeMapUnitScale="3x:0,0,0,0,0,0" shapeSizeType="0" shapeSizeUnit="MM" shapeSizeX="0" shapeSizeY="0" shapeType="0">
       <symbol alpha="1" clip_to_extent="1" force_rhr="0" frame_rate="10" is_animated="0" name="fillSymbol" type="fill">
        <data_defined_properties>
         <Option type="Map">
          <Option name="name" type="QString" value=""/>
          <Option name="properties"/>
          <Option name="type" type="QString" value="collection"/>
         </Option>
        </data_defined_properties>
        <layer class="SimpleFill" enabled="1" id="" locked="0" pass="0">
         <Option type="Map">
          <Option name="border_width_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
          <Option name="color" type="QString" value="255,255,255,255,rgb:1,1,1,1"/>
          <Option name="joinstyle" type="QString" value="bevel"/>
          <Option name="offset" type="QString" value="0,0"/>
          <Option name="offset_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
          <Option name="offset_unit" type="QString" value="MM"/>
          <Option name="outline_color" type="QString" value="128,128,128,255,rgb:0.5019608,0.5019608,0.5019608,1"/>
          <Option name="outline_style" type="QString" value="no"/>
          <Option name="outline_width" type="QString" value="0"/>
          <Option name="outline_width_unit" type="QString" value="MM"/>
          <Option name="style" type="QString" value="solid"/>
         </Option>
         <data_defined_properties>
          <Option type="Map">
           <Option name="name" type="QString" value=""/>
           <Option name="properties"/>
           <Option name="type" type="QString" value="collection"/>
          </Option>
         </data_defined_properties>
        </layer>
       </symbol>
      </background>
      <shadow shadowBlendMode="6" shadowColor="0,0,0,255,rgb:0,0,0,1" shadowDraw="0" shadowOffsetAngle="135" shadowOffsetDist="1" shadowOffsetGlobal="1" shadowOffsetMapUnitScale="3x:0,0,0,0,0,0" shadowOffsetUnit="MM" shadowOpacity="0.69999999999999996" shadowRadius="1.5" shadowRadiusAlphaOnly="0" shadowRadiusMapUnitScale="3x:0,0,0,0,0,0" shadowRadiusUnit="MM" shadowScale="100" shadowUnder="0"/>
      <dd_properties>
       <Option type="Map">
        <Option name="name" type="QString" value=""/>
        <Option name="properties"/>
        <Option name="type" type="QString" value="collection"/>
       </Option>
      </dd_properties>
      <substitutions/>
     </text-style>
     <text-format addDirectionSymbol="0" autoWrapLength="0" decimals="3" formatNumbers="0" leftDirectionSymbol="&lt;" multilineAlign="0" placeDirectionSymbol="0" plussign="0" reverseDirectionSymbol="0" rightDirectionSymbol=">" useMaxLineLengthForAutoWrap="1" wrapChar=""/>
     <placement allowDegraded="0" centroidInside="0" centroidWhole="0" dist="0" distMapUnitScale="3x:0,0,0,0,0,0" distUnits="MM" fitInPolygonOnly="0" geometryGenerator="" geometryGeneratorEnabled="0" geometryGeneratorType="PointGeometry" labelOffsetMapUnitScale="3x:0,0,0,0,0,0" layerType="UnknownGeometry" lineAnchorClipping="0" lineAnchorPercent="0.5" lineAnchorTextPoint="CenterOfText" lineAnchorType="0" maxCurvedCharAngleIn="25" maxCurvedCharAngleOut="-25" maximumDistance="0" maximumDistanceMapUnitScale="3x:0,0,0,0,0,0" maximumDistanceUnit="MM" multipartBehavior="LabelLargestPartOnly" offsetType="0" offsetUnits="MM" overlapHandling="PreventOverlap" overrunDistance="0" overrunDistanceMapUnitScale="3x:0,0,0,0,0,0" overrunDistanceUnit="MM" placement="3" placementFlags="9" polygonPlacementFlags="2" predefinedPositionOrder="TR,TL,BR,BL,R,L,TSR,BSR" preserveRotation="1" prioritization="PreferCloser" priority="5" quadOffset="4" repeatDistance="600000000" repeatDistanceMapUnitScale="3x:0,0,0,0,0,0" repeatDistanceUnits="MapUnit" rotationAngle="0" rotationUnit="AngleDegrees" xOffset="0" yOffset="0"/>
     <rendering drawLabels="1" fontLimitPixelSize="0" fontMaxPixelSize="10000" fontMinPixelSize="3" limitNumLabels="0" maxNumLabels="2000" mergeLines="0" minFeatureSize="1" obstacle="0" obstacleFactor="1" obstacleType="0" scaleMax="18000" scaleMin="0" scaleVisibility="1" unplacedVisibility="0" upsidedownLabels="0" zIndex="0"/>
     <dd_properties>
      <Option type="Map">
       <Option name="name" type="QString" value=""/>
       <Option name="properties"/>
       <Option name="type" type="QString" value="collection"/>
      </Option>
     </dd_properties>
     <callout type="simple">
      <Option type="Map">
       <Option name="anchorPoint" type="QString" value="pole_of_inaccessibility"/>
       <Option name="blendMode" type="int" value="0"/>
       <Option name="ddProperties" type="Map">
        <Option name="name" type="QString" value=""/>
        <Option name="properties"/>
        <Option name="type" type="QString" value="collection"/>
       </Option>
       <Option name="drawToAllParts" type="bool" value="false"/>
       <Option name="enabled" type="QString" value="0"/>
       <Option name="labelAnchorPoint" type="QString" value="point_on_exterior"/>
       <Option name="lineSymbol" type="QString" value="&lt;symbol alpha=&quot;1&quot; clip_to_extent=&quot;1&quot; force_rhr=&quot;0&quot; frame_rate=&quot;10&quot; is_animated=&quot;0&quot; name=&quot;symbol&quot; type=&quot;line&quot;>&lt;data_defined_properties>&lt;Option type=&quot;Map&quot;>&lt;Option name=&quot;name&quot; type=&quot;QString&quot; value=&quot;&quot;/>&lt;Option name=&quot;properties&quot;/>&lt;Option name=&quot;type&quot; type=&quot;QString&quot; value=&quot;collection&quot;/>&lt;/Option>&lt;/data_defined_properties>&lt;layer class=&quot;SimpleLine&quot; enabled=&quot;1&quot; id=&quot;{bf3bf7dd-2676-4e42-a339-c8830ecdfb0f}&quot; locked=&quot;0&quot; pass=&quot;0&quot;>&lt;Option type=&quot;Map&quot;>&lt;Option name=&quot;align_dash_pattern&quot; type=&quot;QString&quot; value=&quot;0&quot;/>&lt;Option name=&quot;capstyle&quot; type=&quot;QString&quot; value=&quot;square&quot;/>&lt;Option name=&quot;customdash&quot; type=&quot;QString&quot; value=&quot;5;2&quot;/>&lt;Option name=&quot;customdash_map_unit_scale&quot; type=&quot;QString&quot; value=&quot;3x:0,0,0,0,0,0&quot;/>&lt;Option name=&quot;customdash_unit&quot; type=&quot;QString&quot; value=&quot;MM&quot;/>&lt;Option name=&quot;dash_pattern_offset&quot; type=&quot;QString&quot; value=&quot;0&quot;/>&lt;Option name=&quot;dash_pattern_offset_map_unit_scale&quot; type=&quot;QString&quot; value=&quot;3x:0,0,0,0,0,0&quot;/>&lt;Option name=&quot;dash_pattern_offset_unit&quot; type=&quot;QString&quot; value=&quot;MM&quot;/>&lt;Option name=&quot;draw_inside_polygon&quot; type=&quot;QString&quot; value=&quot;0&quot;/>&lt;Option name=&quot;joinstyle&quot; type=&quot;QString&quot; value=&quot;bevel&quot;/>&lt;Option name=&quot;line_color&quot; type=&quot;QString&quot; value=&quot;60,60,60,255,rgb:0.2352941,0.2352941,0.2352941,1&quot;/>&lt;Option name=&quot;line_style&quot; type=&quot;QString&quot; value=&quot;solid&quot;/>&lt;Option name=&quot;line_width&quot; type=&quot;QString&quot; value=&quot;0.3&quot;/>&lt;Option name=&quot;line_width_unit&quot; type=&quot;QString&quot; value=&quot;MM&quot;/>&lt;Option name=&quot;offset&quot; type=&quot;QString&quot; value=&quot;0&quot;/>&lt;Option name=&quot;offset_map_unit_scale&quot; type=&quot;QString&quot; value=&quot;3x:0,0,0,0,0,0&quot;/>&lt;Option name=&quot;offset_unit&quot; type=&quot;QString&quot; value=&quot;MM&quot;/>&lt;Option name=&quot;ring_filter&quot; type=&quot;QString&quot; value=&quot;0&quot;/>&lt;Option name=&quot;trim_distance_end&quot; type=&quot;QString&quot; value=&quot;0&quot;/>&lt;Option name=&quot;trim_distance_end_map_unit_scale&quot; type=&quot;QString&quot; value=&quot;3x:0,0,0,0,0,0&quot;/>&lt;Option name=&quot;trim_distance_end_unit&quot; type=&quot;QString&quot; value=&quot;MM&quot;/>&lt;Option name=&quot;trim_distance_start&quot; type=&quot;QString&quot; value=&quot;0&quot;/>&lt;Option name=&quot;trim_distance_start_map_unit_scale&quot; type=&quot;QString&quot; value=&quot;3x:0,0,0,0,0,0&quot;/>&lt;Option name=&quot;trim_distance_start_unit&quot; type=&quot;QString&quot; value=&quot;MM&quot;/>&lt;Option name=&quot;tweak_dash_pattern_on_corners&quot; type=&quot;QString&quot; value=&quot;0&quot;/>&lt;Option name=&quot;use_custom_dash&quot; type=&quot;QString&quot; value=&quot;0&quot;/>&lt;Option name=&quot;width_map_unit_scale&quot; type=&quot;QString&quot; value=&quot;3x:0,0,0,0,0,0&quot;/>&lt;/Option>&lt;data_defined_properties>&lt;Option type=&quot;Map&quot;>&lt;Option name=&quot;name&quot; type=&quot;QString&quot; value=&quot;&quot;/>&lt;Option name=&quot;properties&quot;/>&lt;Option name=&quot;type&quot; type=&quot;QString&quot; value=&quot;collection&quot;/>&lt;/Option>&lt;/data_defined_properties>&lt;/layer>&lt;/symbol>"/>
       <Option name="minLength" type="double" value="0"/>
       <Option name="minLengthMapUnitScale" type="QString" value="3x:0,0,0,0,0,0"/>
       <Option name="minLengthUnit" type="QString" value="MM"/>
       <Option name="offsetFromAnchor" type="double" value="0"/>
       <Option name="offsetFromAnchorMapUnitScale" type="QString" value="3x:0,0,0,0,0,0"/>
       <Option name="offsetFromAnchorUnit" type="QString" value="MM"/>
       <Option name="offsetFromLabel" type="double" value="0"/>
       <Option name="offsetFromLabelMapUnitScale" type="QString" value="3x:0,0,0,0,0,0"/>
       <Option name="offsetFromLabelUnit" type="QString" value="MM"/>
      </Option>
     </callout>
    </settings>
   </rule>
  </rules>
 </labeling>
 <blendMode>0</blendMode>
 <featureBlendMode>0</featureBlendMode>
 <layerOpacity>1</layerOpacity>
 <layerGeometryType>1</layerGeometryType>
</qgis>
