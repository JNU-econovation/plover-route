package com.plobber.routing.graphhopper;

import com.graphhopper.reader.ReaderWay;
import com.graphhopper.routing.ev.DecimalEncodedValue;
import com.graphhopper.routing.ev.DecimalEncodedValueImpl;
import com.graphhopper.routing.ev.EdgeIntAccess;
import com.graphhopper.routing.util.parsers.TagParser;
import com.graphhopper.storage.IntsRef;
import com.plobber.routing.repository.HotspotRepository;
import lombok.Getter;

public class PloggingTagParser implements TagParser {

    private final HotspotRepository hotspotRepository;
    
    @Getter
    private final DecimalEncodedValue trashProbEnc;

    public PloggingTagParser(HotspotRepository hotspotRepository) {
        this.hotspotRepository = hotspotRepository;
        this.trashProbEnc = new DecimalEncodedValueImpl("trash_prob", 5, 0.0, 0.032258, false, false, false);
    }

    @Override
    public void handleWayTags(int edgeId, EdgeIntAccess edgeIntAccess, ReaderWay way, IntsRef relationFlags) {
        Double lat = way.getTag("lat", null);
        Double lon = way.getTag("lon", null);

        if (lat == null || lon == null) {
            trashProbEnc.setDecimal(false, edgeId, edgeIntAccess, 0.0);
            return;
        }

        double prob = hotspotRepository.findProbabilityByPoint(lat, lon);

        if (Double.isNaN(prob) || prob < 0.0) {
            prob = 0.0;
        } else if (prob > 0.999998) {
            prob = 0.999998;
        }

        trashProbEnc.setDecimal(false, edgeId, edgeIntAccess, prob);
    }
}
