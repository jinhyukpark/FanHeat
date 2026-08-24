

$(document).ready(function(){
    if (matchMedia("(max-width:600px) , (min-width:1024px) and (max-width:1312px)").matches) {
        $(".search > button").click(function () {
            $(".search, .input").toggleClass("active");
            $("input[type='search']").focus();
            if($('.search_wrap > div').css("display") == "none"){
                jQuery('.search_wrap > div').delay(600).fadeIn(1000);
            } else {
                jQuery('.search_wrap > div').hide();
            }
        });
    }
}); /*검색창 효과*/

