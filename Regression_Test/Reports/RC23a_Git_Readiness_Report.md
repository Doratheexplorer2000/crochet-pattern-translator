# RC23a Git Readiness Report

Date: 2026-07-16

## Files Recommended For Commit

- `Crochet_Translator_Beta_RC23a.py`
- `stitches_1_8e.csv` if not already committed
- `Regression_Test/` documentation, promoted evidence, and pattern notes
- `Test_Pattern_Library/` source images and pattern notes

## Files Not Recommended For Commit

- `.DS_Store` files
- Python bytecode / `__pycache__/`
- local Streamlit runtime cache files
- unreviewed scratch outputs outside `Regression_Test/Reports/`
- personal Downloads/Desktop/Photos Library paths

## Temporary Files Found Before Cleanup

- `.DS_Store`
- `Regression_Test/.DS_Store`
- `Regression_Test/Current_Reference_Build/.DS_Store`
- `Regression_Test/Patterns/.DS_Store`
- `Regression_Test/Reports/.DS_Store`
- `Regression_Test/Reports/RC22e1_Raw_Evidence/.DS_Store`
- `Regression_Test/Reports/RC23_Raw_Evidence/.DS_Store`
- `Regression_Test/Test_Output/.DS_Store`
- `Test_Pattern_Library/.DS_Store`
- `Test_Pattern_Library/Difficult/.DS_Store`
- `Test_Pattern_Library/Real_User/.DS_Store`
- `Test_Pattern_Library/Stable/.DS_Store`
- `Test_Pattern_Library/Stress_Test/.DS_Store`

## Temporary Files Remaining After Cleanup

- None found by final `.DS_Store` audit.

## Absolute Local Path References

- `Regression_Test/Test_Output/Diagnostics/Pattern_005_Flowerpot_Soil_Block_RC20_SelectArea_LeftColumn_Summary.json`
- `Regression_Test/Test_Output/Diagnostics/Pattern_002_Jellycat_Potato_RC20_Whole_Summary.json`
- `Regression_Test/Test_Output/Diagnostics/Pattern_003_Mushroom_Social_Post_RC20_Whole_Summary.json`
- `Regression_Test/Test_Output/Diagnostics/Pattern_002_Jellycat_Potato_RC20_SelectArea_BodyColumn_Summary.json`
- `Regression_Test/Test_Output/Diagnostics/Pattern_003_Mushroom_Social_Post_RC20c_SelectArea_TextOnly_Smoke_Summary.json`
- `Regression_Test/Test_Output/Diagnostics/Pattern_005_Flowerpot_Soil_Block_RC20_SelectArea_RightColumn_Summary.json`
- `Regression_Test/Test_Output/Diagnostics/Pattern_004_Capybara_English_RC20_Whole_Summary.json`
- `Regression_Test/Test_Output/Diagnostics/Pattern_008_French_Rose_Notes_RC20c_Whole_Summary.json`
- `Regression_Test/Test_Output/Diagnostics/Pattern_004_Capybara_English_RC20_SelectArea_BodyText_Summary.json`
- `Regression_Test/Test_Output/Diagnostics/Pattern_007_Fisherman_Hat_RC20c_Whole_Summary.json`
- `Regression_Test/Test_Output/Diagnostics/Pattern_007_Fisherman_Hat_RC20c_SelectArea_RowList_Summary.json`
- `Regression_Test/Test_Output/Diagnostics/Pattern_003_Mushroom_Social_Post_RC20_SelectArea_TextOnly_Summary.json`
- `Regression_Test/Test_Output/Diagnostics/Pattern_006_Carnation_Chart_Page_RC20_SelectArea_Instructions_Summary.json`
- `Regression_Test/Test_Output/Diagnostics/Pattern_006_Carnation_Chart_Page_RC20_Whole_Summary.json`
- `Regression_Test/Test_Output/Diagnostics/Pattern_005_Flowerpot_Soil_Block_RC20_Whole_Summary.json`
- `Regression_Test/Test_Output/Diagnostics/Pattern_005_Flowerpot_Soil_Block_RC20c_SelectArea_LeftColumn_Smoke_Summary.json`
- `Regression_Test/Test_Output/Diagnostics/Pattern_008_French_Rose_Notes_RC20c_SelectArea_FlowerSupport_Summary.json`
- `Regression_Test/Reports/RC20_New_Patterns_Internal_Regression_Data.json`
- `Regression_Test/Reports/RC20c_Select_Area_Display_Proxy_Data.json`
- `Regression_Test/Reports/RC23_Sea_Salt_Phone_Bag_Real_Run/Sea_Salt_Phone_Bag/Run_Summary_RC23.json`

These are historical report artifacts. They should be normalized in a future cleanup if the reports need to be fully portable, but they are not application code.

## Commit Preparation Status

- Application code was not modified by this finalization task.
- Regression framework documents now identify RC23a as Current Reference Build.
- Previous RC21a1 reference has archive metadata.
- Known issues are recorded in `Regression_Test/Notes/Product_Backlog.md`.
