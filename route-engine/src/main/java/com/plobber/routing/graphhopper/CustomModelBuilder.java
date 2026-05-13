package com.plobber.routing.graphhopper;

import com.graphhopper.json.Statement;
import com.graphhopper.json.Statement.Op;
import com.graphhopper.util.CustomModel;
import org.springframework.stereotype.Component;

@Component
public class CustomModelBuilder {

    public CustomModel build(String mode) {
        CustomModel model = new CustomModel();

        if ("PLOGGING".equalsIgnoreCase(mode)) {
            model.addToPriority(Statement.If("trash_prob < 0.3", Op.MULTIPLY, "0.1"));
            model.addToPriority(Statement.ElseIf("trash_prob < 0.6", Op.MULTIPLY, "0.5"));
            model.addToPriority(Statement.If("road_class == MOTORWAY || road_class == TRUNK || road_class == PRIMARY", Op.MULTIPLY, "0.05"));

            model.setDistanceInfluence(50.0);
            
        } else if ("COMFORT".equalsIgnoreCase(mode)) {
            model.addToPriority(Statement.If("trash_prob > 0.8", Op.MULTIPLY, "0.1"));
            model.addToPriority(Statement.ElseIf("trash_prob > 0.5", Op.MULTIPLY, "0.5"));

            model.setDistanceInfluence(70.0);
        }

        return model;
    }
}
