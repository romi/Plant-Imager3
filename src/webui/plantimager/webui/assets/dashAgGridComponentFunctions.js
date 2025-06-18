var dagcomponentfuncs = window.dashAgGridComponentFunctions = window.dashAgGridComponentFunctions || {};

dagcomponentfuncs.DBC_Button_Simple = function (props) {
    const {setData, data} = props;

    function onClick() {
        setData();
    }
    return React.createElement(
        window.dash_bootstrap_components.Button,
        {
            onClick,
            color: props.color,
        },
        props.value
    );
};