package com.plobber.routing.graphhopper;

import com.graphhopper.reader.ReaderWay;
import com.graphhopper.routing.ev.ArrayEdgeIntAccess;
import com.graphhopper.routing.ev.DecimalEncodedValue;
import com.graphhopper.routing.ev.DecimalEncodedValueImpl;
import com.graphhopper.routing.ev.EdgeIntAccess;
import com.graphhopper.routing.ev.EncodedValue;
import com.graphhopper.routing.util.EncodingManager;
import com.plobber.routing.repository.HotspotRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.anyDouble;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class PloggingTagParserTest {

    @Mock
    private HotspotRepository hotspotRepository;

    private PloggingTagParser parser;
    private DecimalEncodedValue trashProbEnc;

    @BeforeEach
    void setUp() {
        parser = new PloggingTagParser(hotspotRepository);
        trashProbEnc = parser.getTrashProbEnc();
        trashProbEnc.init(new EncodedValue.InitializerConfig());
    }

    @Test
    @DisplayName("길(Way) 좌표가 쓰레기 핫스팟에 포함되면 확률이 EncodedValue에 저장되어야 한다.")
    void testHandleWayTags_whenInsideHotspot_thenSetProbability() {
        ReaderWay way = new ReaderWay(1L);
        way.setTag("lat", 37.5665);
        way.setTag("lon", 126.9780);
        
        when(hotspotRepository.findProbabilityByPoint(anyDouble(), anyDouble())).thenReturn(0.83);

        EdgeIntAccess edgeIntAccess = new ArrayEdgeIntAccess(1);
        parser.handleWayTags(0, edgeIntAccess, way, null);

        double storedProb = trashProbEnc.getDecimal(false, 0, edgeIntAccess);
        assertEquals(0.83, storedProb, 0.05);
    }

    @Test
    @DisplayName("핫스팟을 벗어난 지역이면 확률이 0.0으로 저장되어야 한다.")
    void testHandleWayTags_whenOutsideHotspot_thenSetZero() {
        ReaderWay way = new ReaderWay(2L);
        way.setTag("lat", 35.1595);
        way.setTag("lon", 129.1602);
        
        when(hotspotRepository.findProbabilityByPoint(anyDouble(), anyDouble())).thenReturn(0.0);

        EdgeIntAccess edgeIntAccess = new ArrayEdgeIntAccess(1);
        parser.handleWayTags(0, edgeIntAccess, way, null);

        double storedProb = trashProbEnc.getDecimal(false, 0, edgeIntAccess);
        assertEquals(0.0, storedProb, 0.01);
    }

    @Test
    @DisplayName("확률이 1.0을 초과하면 1.0으로 저장되어야 한다.")
    void testHandleWayTags_whenProbExceedsOne_thenClampToOne() {
        ReaderWay way = new ReaderWay(3L);
        way.setTag("lat", 37.5665);
        way.setTag("lon", 126.9780);
        
        when(hotspotRepository.findProbabilityByPoint(anyDouble(), anyDouble())).thenReturn(1.5);

        EdgeIntAccess edgeIntAccess = new ArrayEdgeIntAccess(1);
        parser.handleWayTags(0, edgeIntAccess, way, null);

        double storedProb = trashProbEnc.getDecimal(false, 0, edgeIntAccess);
        assertEquals(1.0, storedProb, 0.01);
    }

    @Test
    @DisplayName("확률이 음수면 0.0으로 저장되어야 한다.")
    void testHandleWayTags_whenProbIsNegative_thenClampToZero() {
        ReaderWay way = new ReaderWay(4L);
        way.setTag("lat", 37.5665);
        way.setTag("lon", 126.9780);
        
        when(hotspotRepository.findProbabilityByPoint(anyDouble(), anyDouble())).thenReturn(-0.5);

        EdgeIntAccess edgeIntAccess = new ArrayEdgeIntAccess(1);
        parser.handleWayTags(0, edgeIntAccess, way, null);

        double storedProb = trashProbEnc.getDecimal(false, 0, edgeIntAccess);
        assertEquals(0.0, storedProb, 0.01);
    }

    @Test
    @DisplayName("확률이 NaN(결측치)이면 0.0으로 저장되어야 한다.")
    void testHandleWayTags_whenProbIsNaN_thenSetZero() {
        ReaderWay way = new ReaderWay(5L);
        way.setTag("lat", 37.5665);
        way.setTag("lon", 126.9780);
        
        when(hotspotRepository.findProbabilityByPoint(anyDouble(), anyDouble())).thenReturn(Double.NaN);

        EdgeIntAccess edgeIntAccess = new ArrayEdgeIntAccess(1);
        parser.handleWayTags(0, edgeIntAccess, way, null);

        double storedProb = trashProbEnc.getDecimal(false, 0, edgeIntAccess);
        assertEquals(0.0, storedProb, 0.01);
    }
}
