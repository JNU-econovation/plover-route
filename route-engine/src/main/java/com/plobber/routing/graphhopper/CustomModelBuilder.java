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
            buildPloggingModel(model);
        } else if ("COMFORT".equalsIgnoreCase(mode)) {
            buildComfortModel(model);
        }

        return model;
    }

    private void buildPloggingModel(CustomModel model) {
        model.addToPriority(Statement.If("trash_prob >= 0.95", Op.MULTIPLY, "2.5"));
        model.addToPriority(Statement.ElseIf("trash_prob >= 0.9", Op.MULTIPLY, "2.0"));
        model.addToPriority(Statement.ElseIf("trash_prob >= 0.7", Op.MULTIPLY, "1.5"));
        model.addToPriority(Statement.ElseIf("trash_prob >= 0.5", Op.MULTIPLY, "1.0"));
        model.addToPriority(Statement.ElseIf("trash_prob >= 0.3", Op.MULTIPLY, "0.5"));
        model.addToPriority(Statement.Else(Op.MULTIPLY, "0.1"));

        model.addToPriority(Statement.If(
                "road_class == MOTORWAY || road_class == TRUNK || road_class == PRIMARY",
                Op.MULTIPLY, "0.05"));

        model.setDistanceInfluence(30.0);
    }

    private void buildComfortModel(CustomModel model) {
        model.addToPriority(Statement.If("trash_prob > 0.8", Op.MULTIPLY, "0.1"));
        model.addToPriority(Statement.ElseIf("trash_prob > 0.5", Op.MULTIPLY, "0.5"));

        model.setDistanceInfluence(70.0);
    }
}
